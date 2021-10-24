import numpy as np
from geopy import geocoders
import csv
import pickle
import os
import time
import matplotlib.pyplot as plt

with open("username.txt", "r") as f:
    username = f.read()

gn = geocoders.GeoNames(username=username)
CAP_MIN = 5
CAP_MAX = 10  # pretty much random, but if we had data on this it could be easily adjusted
LOAD_MIN = 0
LOAD_MAX = 40
num_points = 1000
DEG_TO_KM = 111 # based on https://www.nhc.noaa.gov/gccalc.shtml
KM_TO_HR = 60  # assume an average speed of 60 km/h
TIME_PER_TEST = 1.0

class Hospital():
    def __init__(self, pos, name, cap, load, idx):
        self.pos = pos  # GPS coordinates
        self.name = name # name of hospital
        self.cap = cap  # the number of available microscopy kits (or technicians)
        self.idx = idx # so we can access it in the other variables
        self.load = load # the current number of tests to process
        self.tests_per_hour = TIME_PER_TEST / cap #the amount of tests that can be done per hour

    def get_time_to_process(self, pos, amount):
        # very simple model that assumes no other tests will be coming in as yours is being transported to the hospital
        # it also assumes that trucks travel instantaneously at 60km/hr exactly from each point
        travel_time = self.get_distance(pos)*KM_TO_HR
        wait_time = max(0, (self.load / self.tests_per_hour) - travel_time)
        test_time = amount / self.tests_per_hour
        return travel_time*2 + wait_time + test_time  # this isnt actually the time to receive results, as that will be based on the speed of the mail


    def get_remaining(self):
        return self.cap-self.load

    def get_distance(self, pos):
        #Returns the approximate distance in kilometers. A higher fidelity prototype would use a Google Maps API to get the actual distance.
        return DEG_TO_KM*np.linalg.norm(self.pos - pos, 1)

    def __repr__(self):
        return f"{self.name[1:-1]} - {self.load}/{self.cap}"


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
        print(f"Found: ({key}: {town_geocodes[key]})")
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

def rand_cap():
    # a higher fidelity prototype would involve data from https://pdfs.semanticscholar.org/e5a7/34314127b3b3c62f2befbe704ebc0cd3e635.pdf
    return np.random.randint(CAP_MIN, CAP_MAX)

def rand_load():
    # a higher fidelity prototype would involve data from https://pdfs.semanticscholar.org/e5a7/34314127b3b3c62f2befbe704ebc0cd3e635.pdf
    return np.random.randint(LOAD_MIN, LOAD_MAX)

def extract_pos(geocode):
    return [float(geocode.raw["lat"]), float(geocode.raw["lng"])]

def simple_recommendation():
    # A higher fidelity prototype would take into account more factors
    town_name = input("Enter the name of your town: ")
    try:
        geocode = gn.geocode(f"{town_name}, Nigeria")
    except:
        print("Town could not be found")
        return
    pos = extract_pos(geocode)
    number_tests = float(input("Enter the number of blood samples to be processed: "))
    best = np.inf
    best_hospital = None
    for hosp in idx_to_hospital.values():
        total_time = hosp.get_time_to_process(pos, number_tests)
        if total_time < best:
            best = total_time
            best_hospital = hosp
    print(f"The best hospital to travel to is: {hosp}")
    print(f"The tests will take approximately {best} hours to process")

loc_arr = np.array([extract_pos(geo) for geo in town_geocodes.values()])
loc_mins, loc_maxs = np.min(loc_arr, axis=0), np.max(loc_arr, axis=0)
#loc_grid = pos_to_idx(loc_arr, loc_mins, loc_maxs)
idx_to_town = {i:k for i,k in enumerate(town_geocodes.keys())}
idx_to_hospital = {i:Hospital(loc,name, rand_cap(), rand_load(), i)  for i,(loc,name) in enumerate(zip(loc_arr, town_geocodes.keys()))}

simple_recommendation()

