#!/usr/bin/env python3
import socket
from flask import Flask, redirect, url_for, request
import os
app = Flask(__name__)

@app.route('/', methods=['POST', 'GET'])
def hello():
    if request.method == "POST":
        return "you posted"
    else:
        return "yooooooo what up"


@app.route("/index/<inpt>")
def weird(inpt):
    return f"argument was {inpt}"


@app.route("/usr/<name>")
def greetings(name):
    if name == "root":
        return redirect(url_for("weird", inpt=name))
    else:
        return redirect(url_for("weird", inpt="INCORRECT"))

if __name__ == "__main__":
    addr = socket.gethostbyname(socket.gethostname())
    app.run(host=addr, port=2222, debug=False)
