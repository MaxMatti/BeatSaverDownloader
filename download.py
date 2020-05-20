#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests

def main():
    searchterm = input("Search term: ")
    i = 0
    songs = []
    session = requests.Session()
    session.headers.update({"User-Agent": "Wget/1.20.3 (linux-gnu)"}) # required in order not to get blocked by cloudflare
    while True:
        r = session.get("https://beatsaver.com/api/search/text/" + str(i) + "?q=" + searchterm)
        result = r.json()
        songs += result["docs"]
        if result["nextPage"]:
            i = result["nextPage"]
        else:
            break
    for s in songs:
        print(s["key"] + ": " + s["metadata"]["songName"] + " - " + s["metadata"]["songSubName"] + " by " + s["metadata"]["songAuthorName"] + " - " + s["metadata"]["levelAuthorName"])
        print("Link: https://beatsaver.com" + s["downloadURL"])

if __name__ == '__main__':
    main()
