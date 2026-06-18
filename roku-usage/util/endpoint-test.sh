#!/bin/bash

# 
# Test Roku endpoints
# 

ROKU_IP=`cat .roku-ip`

#curl http://${ROKU_IP}:8060/query/device-info
curl http://${ROKU_IP}:8060/query/active-app
curl http://${ROKU_IP}:8060/query/media-player


