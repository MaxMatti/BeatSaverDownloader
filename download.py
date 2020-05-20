#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# author: Max Staff <max@xgme.de>
# original repo url: https://github.com/MaxMatti/BeatSaverDownloader

import atexit
import os
import requests
import shutil
import sys
import termios
import time
import threading

completion = {"songs": set()}
songs = {}
running = True
t = {
    "inputlock": threading.Lock(),
    "outputlock": threading.Lock(),
    "input": "",
    "status": "",
    "termios": None,
    "inputpos": 0,
    "outputpos": 0,
}

def exit_handler():
    global t
    t["input"] = ""
    print()
    fd = sys.stdin.fileno()
    termios.tcsetattr(fd, termios.TCSADRAIN, t["termios"])

def init_printer():
    global t
    fd = sys.stdin.fileno()
    t["termios"] = termios.tcgetattr(fd)
    after = termios.tcgetattr(fd)
    after[3] &= ~termios.ICANON & ~termios.ECHO
    termios.tcsetattr(fd, termios.TCSADRAIN, after)

def print(*args, sep = " ", end = "\n", flush = False, display_status = True):
    global t
    file = sys.stdout
    writestr = str(sep).join(str(arg) for arg in args) + end
    if "\n" in writestr or "\r" in writestr:
        n = writestr.rfind("\n")
        if n == len(writestr) - 1:
            linelen = -1
        else:
            linelen = len(writestr) - max(n, writestr.rfind("\r")) - 1
    else:
        linelen = t["outputpos"] + len(writestr)
    with t["outputlock"]:
        if t["input"] != "" or t["status"] != "":
            writestr = ("\033[A" * t["status"].count("\n")) + writestr
            if t["outputpos"] >= 0:
                writestr = "\033[A" + writestr
            writestr = "\033[K" + writestr
            if t["outputpos"] > 0:
                writestr = "\r\033[" + str(t["outputpos"]) + "C" + writestr
            else:
                writestr = "\r" + writestr
            if linelen >= 0:
                writestr += "\n"
            if display_status:
                writestr += t["status"]
            writestr += t["input"]
            t["outputpos"] = linelen
        file.write(writestr)
        if flush:
            file.flush()

def press_ctrl_left(input_text, pos):
    while True:
        sys.stdout.write(chr(27) + "[D")
        pos -= 1
        if pos - 1 < 0 or input_text[pos - 1] == " ":
            break
    return pos

def press_ctrl_right(input_text, pos):
    while True:
        sys.stdout.write(chr(27) + "[C")
        pos += 1
        if pos >= len(input_text) or (pos + 1 < len(input_text) and input_text[pos + 1]) == " ":
            break
    return pos

def input(*args, **kwargs):
    global t
    if not "end" in kwargs:
        kwargs["end"] = "" # use different default value
    if not "sep" in kwargs:
        kwargs["sep"] = " " # default value needed for this function
    kwargs["flush"] = True
    print(*args, **kwargs)
    with t["inputlock"]:
        pos = 0
        input_text = ""
        input_start = kwargs["sep"].join(str(x) for x in args) + kwargs["end"]
        with t["outputlock"]:
            t["input"] = input_start + input_text
            t["inputpos"] = pos + len(input_start)
        while True:
            key = sys.stdin.read(1)
            if ord(key) == 127: # backspace
                if pos > 0:
                    with t["outputlock"]:
                        sys.stdout.write("\b" + input_text[pos:] + " " + ("\b" * (len(input_text) - pos + 1)))
                        input_text = input_text[:pos-1] + input_text[pos:]
                        pos -= 1
                        t["input"] = input_start + input_text
                        t["inputpos"] = pos + len(input_start)
            elif ord(key) == 27: # arrow keys
                control_code = sys.stdin.read(2)
                if control_code == "[2": # insert
                    sys.stdin.read(1) # discard "~"
                elif control_code == "[3": # del
                    sys.stdin.read(1) # discard "~"
                elif control_code == "[5": # page-up
                    sys.stdin.read(1) # discard "~"
                elif control_code == "[6": # page-down
                    sys.stdin.read(1) # discard "~"
                elif control_code == "[A": # up
                    pass
                elif control_code == "[B": # down
                    pass
                elif control_code == "[C": # right
                    if pos < len(input_text):
                        with t["outputlock"]:
                            sys.stdout.write(key + control_code)
                            pos += 1
                elif control_code == "[D": # left
                    if pos > 0:
                        with t["outputlock"]:
                            sys.stdout.write(key + control_code)
                            pos -= 1
                elif control_code == "[F": # end
                    with t["outputlock"]:
                        sys.stdout.write((chr(27) + "[C") * (len(input_text) - pos))
                        pos = len(input_text)
                elif control_code == "[H": # home
                    with t["outputlock"]:
                        sys.stdout.write((chr(27) + "[D") * pos)
                        pos = 0
                elif control_code == "0c": # rxvt: ctrl+right
                    with t["outputlock"]:
                        pos = press_ctrl_right(input_text, pos)
                elif control_code == "0d": # rxvt: ctrl+left
                    with t["outputlock"]:
                        pos = press_ctrl_left(input_text, pos)
                elif control_code == "[1": # xterm: ctrl+...
                    control_code += sys.stdin.read(3)
                    if control_code == "[1;5C": # xterm: ctrl+right
                        with t["outputlock"]:
                            pos = press_ctrl_right(input_text, pos)
                    elif control_code == "[1;5D": # xterm: ctrl+left
                        with t["outputlock"]:
                            pos = press_ctrl_left(input_text, pos)
                    else:
                        sys.stderr.write("Unknown control code: " + control_code)
                        sys.stderr.flush()
                else:
                    sys.stderr.write("Unknown control code: " + control_code)
                    sys.stderr.flush()
            elif ord(key) > 31:
                with t["outputlock"]:
                    sys.stdout.write(key)
                    if pos < len(input_text):
                        sys.stdout.write(input_text[pos:] + "\b" * (len(input_text) - pos))
                    input_text = input_text[:pos] + key + input_text[pos:]
                    t["input"] = input_start + input_text
                    t["inputpos"] = pos + len(input_start)
                    pos += 1
            elif key == "\t":
                suggestion = completer(input_text, pos)
                if len(suggestion) == 0:
                    print("No autocompletion found.")
                elif len(suggestion) == 1:
                    with t["outputlock"]:
                        sys.stdout.write(suggestion[0][len(input_text):])
                        input_text = suggestion[0]
                        pos = len(input_text)
                        t["input"] = input_start + input_text
                        t["inputpos"] = pos + len(input_start)
                else:
                    print(suggestion)
            elif key == "\n":
                with t["outputlock"]:
                    sys.stdout.write(key)
                    t["input"] = ""
                    t["inputpos"] = 0
                    t["outputpos"] = -1
                    sys.stdout.flush()
                break
            else:
                sys.stderr.write("Unknown key: " + str(ord(key)) + "\n")
                sys.stderr.flush()
            sys.stdout.flush()
        input_start = ""
        result = input_text
        input_text = ""
        return result

def status(*args, sep = " ", end = "\n", flush = False):
    file = sys.stdout
    writestr = str(sep).join(str(arg) for arg in args) + end
    print(writestr, end="", flush = flush, display_status = False)
    t["status"] = writestr

def completer(text: str, pos: int = -1):
    return [song for song in completion["songs"] if song.startswith(text[:pos]) and text[pos:] in song[pos:]]

def get_session():
    session = requests.Session()
    session.headers.update({"User-Agent": "Wget/1.20.3 (linux-gnu)"}) # required in order not to get blocked by cloudflare
    return session

def search(searchterm: str):
    global songs, running
    i = 0
    while running:
        r = get_session().get("https://beatsaver.com/api/search/text/" + str(i) + "?q=" + searchterm)
        result = r.json()
        if not running:
            return
        for s in result["docs"]:
            songs[s["key"]] = s
            print("[" + (" " * (5 - len(s["key"]))) + s["key"] + " ]: " + s["metadata"]["songName"] + " - " + s["metadata"]["songSubName"] + " by " + s["metadata"]["songAuthorName"] + " - " + s["metadata"]["levelAuthorName"])
            #print("Link: https://beatsaver.com" + s["downloadURL"])
            completion["songs"].add(s["key"])
        if result["nextPage"]:
            i = result["nextPage"]
        else:
            break
    if len(songs) == 0:
        print("No songs found!")

def watch_download(size: int, name: str, filename: str):
    for i in range(5):
        try:
            with open(filename, "rb") as f:
                while True:
                    time.sleep(0.1)
                    pos = os.fstat(f.fileno()).st_size
                    percent = str(100 * pos // size)
                    status(name + ": " + (" " * (len(str(size)) - len(str(pos)))) + str(pos) + "/" + str(size) + " (" + (" " * (3 - len(percent))) + percent + "%)", end="\r")
                    if pos >= size:
                        status(name + ": " + str(pos) + "/" + str(size) + " (done)", end="\r")
                        return
        except FileNotFoundError:
            pass
        time.sleep(1)

def download(songId: str, url: str):
    t = False
    filename = songId + ".zip"
    with get_session().get(url, stream=True) as r:
        r.raw.decode_content = True
        if r.headers['Content-length']:
            t = threading.Thread(target = watch_download, args = (int(r.headers['Content-length']), songId, filename))
            t.start()
        with open(filename, 'wb') as f:
            shutil.copyfileobj(r.raw, f)
        if t:
            t.join()

def main():
    global songs, running
    atexit.register(exit_handler)
    init_printer()
    threads = []

    searchterm = input("Search term: ")
    t = threading.Thread(name = "searching for \"" + searchterm + "\"", target = search, args = (searchterm, ))
    t.start()
    while True:
        dl = input("Download: ")
        if len(dl) == 0:
            break
        if not dl in songs:
            break
        url = "https://beatsaver.com" + songs[dl]["downloadURL"]
        t = threading.Thread(name = "downloading " + dl, target = download, args = (dl, url))
        t.start()
        threads.append(t)
    running = False
    while True:
        remaining_downloads = [t for t in threads if t.is_alive()]
        if len(remaining_downloads) == 0:
            break
        for i in threads:
            i.join(1)

if __name__ == '__main__':
    main()
