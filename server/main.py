import numpy as np
from geopy import geocoders
import csv
import pickle
import time
import matplotlib.pyplot as plt
import geopandas as gpd
import os
import pandas as pd
from datetime import datetime
import gmaps
#import googlemaps
from geopy.distance import geodesic
import threading as th
from bokeh.models import GMapOptions, TextInput, CustomJS, Div, TapTool, ColumnDataSource
from bokeh.plotting import gmap, figure, curdoc
from bokeh.models.annotations import Title
from bokeh.layouts import grid
import json

from tornado.ioloop import IOLoop
from tornado import gen
from bokeh.util.session_id import generate_session_id
from bokeh.server.server import Server
from bokeh.client import pull_session
from bokeh.embed import server_document, server_session
from bokeh.application.application import Application
from bokeh.application.handlers.function import FunctionHandler
import socket
from flask import Flask, render_template, request
import threading as th

app = Flask(__name__)
ip_addr = socket.gethostbyname(socket.gethostname())
lock = th.Lock()
lock2 = th.Lock()
lock3 = th.Lock()
np.random.seed(50)

def _default(self, obj):
    return getattr(obj.__class__, "to_json", _default.default)(obj)

_default.default = json.JSONEncoder().default
json.JSONEncoder.default = _default

with open("username.txt", "r") as f:
    username = f.read()

gn = geocoders.GeoNames(username=username)
CAP_MIN = 5
CAP_MAX = 10  # pretty much random, but if we had data on this it could be easily adjusted
LOAD_MIN = 0
LOAD_MAX = 40

num_points = 1000
DEG_TO_KM = 111 # based on https://www.nhc.noaa.gov/gccalc.shtml
KM_TO_HR = 1/60  # assume an average speed of 60 km/h
TIME_PER_TEST = 1.0 # number of hours to do one test
INIT_LAT = 9.0820
INIT_LNG = 8.6753
INIT_ZOOM = 7

class Hospital():
    def __init__(self, pos, name, idx):
        self.pos = pos  # GPS coordinates
        self.name = name # name of hospital
        hospital_name, location = self.name[2:-2].split(",")
        self.nice_name = ", ".join((hospital_name[:-1], location[2:]))
        self.rate = init_rate()  # the current rate of testing (in number of tests performed per hour)
        self.last_time = None
        self.idx = idx # so we can access it in the other variables
        self.load = init_load() # the current number of tests to process
        if self.idx == 584:
            self.load = 5
            #print("hi", self)
        self.uuid = str(hash(f"{self.name}{self.pos}{np.random.randn}"))
        self.gamma = 0.2   # for ewma

    def get_time_to_process(self, pos, amount):
        # very simple model that assumes no other tests will be coming in as yours is being transported to the hospital
        # it also assumes that trucks travel instantaneously at 60km/hr exactly from each point
        travel_time = self.get_distance(pos)*KM_TO_HR
        wait_time = max(0, (self.load / self.rate) - travel_time)
        test_time = amount / self.rate
        return travel_time*2 + wait_time + test_time  # this isnt actually the time to receive results, as that will be based on the speed of the mail

    def get_travel_time(self, pos, amount):
        return self.get_distance(pos)*KM_TO_HR

    def get_distance(self, pos):
        #Returns the approximate distance in kilometers. A higher fidelity prototype would use a Google Maps API to get the actual distance.
        return DEG_TO_KM*np.linalg.norm(self.pos - pos, 1)

    def increase_load(self, amount):
        self.load += amount

    def update_rate(self, new_time):
        if self.last_time:
            time_diff = new_time - self.last_time # time in seconds to process most recent sample
            self.rate = self.rate*(1-self.gamma) + 60/(time_diff+1e-8)*self.gamma
        else:
            self.last_time = new_time
        self.load = max(self.load - 1, 0)

    def to_json(self):
        return {"idx": self.idx,
                "load": self.load,
                "uuid": self.uuid,
                "name": self.name,
                "rate": self.rate,
                "pos": self.pos,
                "str_repr": str(self)}


    def __repr__(self):
        #return f"{self.name[1:-1]} - {self.load}/{self.rate} ({self.uuid})"
        return f"<b>{self.nice_name}</b><br>Rate of processing (samples/hour): {self.rate:.2f} \
    <br>\nCurrent estimated number of samples to process: {self.load}\n<br>"

class HospitalJSON(Hospital, json.JSONEncoder):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    def default(self, o):
        return json.JSONEncoder.default(self, o.__dict__)


with open("hcf.csv", "r") as f:
    hospitals = list(csv.reader(f))[1:]

fname = "town_geo.pickle"
if os.path.exists(fname):
    with open(fname, "rb") as p:
        town_geocodes = pickle.load(p)
else:
    town_geocodes = {}

for hospital in hospitals:
    key = f"{hospital[2], hospital[4]}"
    try:
        town_geocodes[key]
        #print(f"Found: ({key}: {town_geocodes[key]})")
    except KeyError:
        try:
            geocode = gn.geocode(f"{hospital[4]}, Nigeria")
            time.sleep(2.0)
            if geocode:
                town_geocodes[key] = geocode
                print(f"Retrieved: ({key}: {town_geocodes[key]})")
            else:
                print(f"No data found on '{hospital[4]}, Nigeria'")
        except:
            print(f"TIMEOUT on {key}")

with open(fname, "wb") as f:
    pickle.dump(town_geocodes, f)

assert len(hospitals) == len(town_geocodes)  # make sure we've retrieved every hospital

def pos_to_idx(pos, mins, maxs):
    x = pos - mins
    x /= (maxs-mins)
    x *= num_points
    return x.astype(np.int64)

def init_rate():
    #return np.random.randint(CAP_MIN, CAP_MAX)
    return 2

def init_load():
    return np.random.randint(LOAD_MIN, LOAD_MAX)
    #return 1

def extract_pos(geocode):
    return [float(geocode.raw["lng"]), float(geocode.raw["lat"])]

def simple_recommendation(pos, number_tests, basis):
    # A higher fidelity prototype would take into account more factors
    best = np.inf
    best_hospital = None
    for hosp in idx_to_hospital.values():
        total_time = basis(hosp, pos, number_tests)
        #print(total_time, hosp)
        if total_time < best:
            #print("found improve", best, best_hospital)
            best = total_time
            best_hospital = hosp
    print(f"\tThe best hospital to travel to is: {best_hospital.nice_name}")
    print(f"\tThe tests will take approximately {best_hospital.get_time_to_process(pos, number_tests)} hours to process")
    return best_hospital.pos, pos, best_hospital

def get_request():
    town_name = input("Enter the name of your town: ")
    pos = retrieve_loc(town_name)[0]
    if pos:
        number_tests = float(input("Enter the number of blood samples to be processed: "))
        return pos, number_tests

def retrieve_loc(town_name):
    try:
        geocode = gn.geocode(f"{town_name}, Nigeria")
    except:
        return
    if geocode is None:
        return
    pos = extract_pos(geocode)
    return pos, str(geocode)


loc_arr = np.array([extract_pos(geo) for geo in town_geocodes.values()])
loc_mins, loc_maxs = np.min(loc_arr, axis=0), np.max(loc_arr, axis=0)
idx_to_town = {i:k for i,k in enumerate(town_geocodes.keys())}
idx_to_hospital = {i:Hospital(loc,name, i)  for i,(loc,name) in enumerate(zip(loc_arr, town_geocodes.keys()))}
df = pd.DataFrame([(loc[0], loc[1], i, Hospital(loc, name, i)) for i,(loc,name) in enumerate(zip(loc_arr, town_geocodes.keys()))],
                  columns=["longitude", "latitude", "index", "hospital_info"])

src = ColumnDataSource(df)
changes = []
confirmation_data = ColumnDataSource(data=dict(candidate=[""]))
loc_changes = []
candidate_pos = None

with open("key.txt", "r") as f:
    api_key = f.read()

def location_submitted(attr, old, new):
    global candidate_pos
    potential_pos = retrieve_loc(new)
    with lock2:
        if potential_pos:
            loc_changes.append(potential_pos[1])
            candidate_pos = potential_pos[0]
        else:
            loc_changes.append(f"Place '{new}' not found")
            candidate_pos = None


def samples_submitted(attr, old, new):
    try:
        num = int(new)
    except:
        try:
            num = int(old)
        except:
            return
    print(candidate_pos)
    if candidate_pos:
        print("Optimized recommendation:")
        _,_,ihosp = simple_recommendation(candidate_pos, num, Hospital.get_time_to_process)
        print("Reference recommendation:")
        _,_,ohosp = simple_recommendation(candidate_pos, num, Hospital.get_travel_time)
        ihosp.increase_load(num)
        update_hospital(ihosp.idx)

def bokeh_doc(doc):
    global df
    gmap_options = GMapOptions(lat=INIT_LAT, lng=INIT_LNG, map_type='roadmap', zoom=INIT_ZOOM)
    info_box = Div(text="",
                    style={"font-size": "18px",
                           "margin": "100px 0px 0px 100px",
                           "border": "5px solid gray",
                           "border-radius": "5px",
                           "width": "500px"
                            })

    mmap = gmap(api_key, gmap_options, title=Title(text='Malaria and Hopsital Heat Map: Nigeria', standoff=40),
             width=1200, height=800)
    points = mmap.circle("longitude", "latitude", size=12, alpha=0.5, color='red', source=src)

    click_callback = CustomJS(args=dict(source=src, info_box=info_box), code="""
                                  const idxs = cb_data.source.selected.indices;
                                  const src_data = source.data;
                                  info_box.text = src_data.hospital_info[idxs[0]].str_repr;
                              """)
    mmap.add_tools(TapTool(callback=click_callback))

    confirmation_info = Div(text="",
                    style={"font-size": "12px",
                           "border": "1px solid gray",
                           "border-radius": "1px",
                           "width": "500px"
                            })
    location_search = TextInput(title="Enter a location:")
    location_search.on_change("value", location_submitted)
    location_search.js_on_change("value", CustomJS(args=dict(candidate_data=confirmation_data, info_box=confirmation_info), code="""
                                                  console.log(candidate_data.data);
                                                  console.log(candidate_data.data.candidate);
                                                  info_box.text = 'Identified place ' + candidate_data.data.candidate[0];
                                                   """))

    sample_search = TextInput(title="Enter number of samples:")
    sample_search.on_change("value", samples_submitted)
    #sample_search.js_on_change("value", CustomJS(args=dict(candidate_data=confirmation_data, info_box=confirmation_info), code="""
    #                                             confirmation_info.text = 'Identified place ' + candidate_data.data[0].candidate<br>;
    #                                                """))
    @gen.coroutine
    def modify_info():
        with lock:
            while changes:
                src.patch(changes.pop())

    @gen.coroutine
    def modify_candidate():
        with lock2:
            while loc_changes:
                confirmation_data.patch({"candidate": [(0, loc_changes.pop())]})
    doc.add_periodic_callback(modify_info, 500)
    doc.add_periodic_callback(modify_candidate, 100)
    doc.add_root(grid([[mmap, info_box], [location_search], [confirmation_info], [sample_search]]))

def update_hospital(idx):
    with lock:
        changes.append({"hospital_info": [(idx, idx_to_hospital[idx])]})


@app.route("/nano")
def arduino_request():
    global changes
    if request.method == "GET":
        try:
            time_stamp  = request.headers["time_finished"]
            hospital_id = int(request.headers["id"])
            hosp = idx_to_hospital[hospital_id]
            hosp.update_rate(float(time_stamp))
            #print(hosp)
            update_hospital(hospital_id)
            #def change_applier():
            #src.patch({"hospital_info": [(hospital_id, [hosp])]})

            #IOLoop.current().add_callback(change_applier)
            #src.patch()
            return "good job"
        except KeyError:
            return "server error"
    else:
        return "what are you even trying to do"


@app.route("/")
def map_page():
    script = server_session(url=f"http://{ip_addr}:5006/server", session_id=generate_session_id())
    return render_template("empty.html", script=script, template="Flask")


def bokeh_worker():
    server = Server({"/server": bokeh_doc}, io_loop=IOLoop(), allow_websocket_origin=[f"{ip_addr}:2222"])
    server.start()
    server.io_loop.start()

th.Thread(target=bokeh_worker).start()

if __name__ == "__main__":
    app.run(host=ip_addr, port=2222, debug=False)






