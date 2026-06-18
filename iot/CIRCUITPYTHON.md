# Adafruit Blinka & CircuitPython Notes

The <a href="https://github.com/adafruit/Adafruit_Blinka">Blinka Library</a> (released 2017) is a Circuitpython 
compatibility layer from Adafruit for using their peripherals on
single board computers and even desktop/laptop systems that run a full Linux operating system. It is designed
to have the same API as Circuitpython.

Circuitpython (released 2017) is a derivative of Micropython (released in 2014) both of which run
on bare metal microcontrollers.

## Documentation and API Reference

https://docs.circuitpython.org/en/latest/README.html

## Install

Debian 11 wants this in a virtualenv.

python3 -m venv ~/mywork

~/mywork/bin/pip3 install adafruit-circuitpython-matrixkeypad

## Usage

### Board module

When this module is imported, a set of pin definitions will be available based on the detected board.

<b>dir(board)</b> will list the attributes for this module.

