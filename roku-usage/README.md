# Roku usage tracker

This folder contains a small Roku ECP client for discovering devices, polling their current state, and logging usage into SQLite.

The poller now reduces Roku signals to a finite system state: `OFF`, `IDLE`, or `STREAMING`.

The scripts use only the Python standard library, so `pip install -r requirements.txt` is optional and does not install anything.

## Scripts

`roku-discover.py` lists Roku TVs on the local network.

`roku-poll.py` polls one Roku host once and can optionally store the sample in a database.

`roku-iot.py` runs continuously, discovering Roku devices and logging repeated samples to SQLite.

`roku-database.py` initializes the database and prints a simple usage report.
