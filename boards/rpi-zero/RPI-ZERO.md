# Raspberry Pi Zero / Pi Zero W

I have two of these boards:

* Pi Zero
* Pi Zero W

## TTL Serial

Serial console can be enabled via the **raspi-config** program.

```
sudo raspi-config
```

Select '3 Interface Options' and then 'I5 Serial Port Enable'

Adafruit PL2303 USB Serial connections:

<img src="serial_pins.jpg">

Red --> 2
Black --> 4
White --> 6
Green --> 8

Debian console settings: 115,200 N81
