#!/usr/bin/env bash

# This for those who do not want to wrestle with python versions

# You can run this file directly or add the below command as function to your 
# shell login config of choice. E.g. ~/.zprofile:
# function eigengen {
#   docker run \
#     --env OPENAI_API_KEY \
#     --rm -i \
#     --volume "$( pwd ):/usr/src/app" \
#     eigengen "$@" 
# }

docker run \
--env OPENAI_API_KEY \
--rm -i \
--volume "$( pwd ):/usr/src/app" \
eigengen "$@" 
