# Example data service via Tritom

This is a dockerized web app that responds to data requests by sending static data. Data requests and datasets are sent via Tritom demo data intermediation service.

This repository assumes a Linux environment. Running this project on macOS, Windows (without WSL), or other operating systems is not natively supported.

This repository was published by the Datatalouskasvattamo project.

## Overview of data transfer via Tritom

### Tritom data channels

Here's a simplified description about how datasets are sent and received via Tritom.

![Data sharing via Tritom simplified](/charts/Tritom_application.drawio.png)

1. To enable (one-way) data transfer via Tritom, the sending or the receiving organization requests to open a data channel in Tritom. The other organization accepts the request in Tritom.
2. Application B sends a dataset to Application A through one data channel.
3. Application A receives the dataset from their Tritom connector, processes it and possibly responds through another data channel.
4. Application B receives the response from their Tritom connector.

This repo contains source code for Application A, i.e. web server that provides static data on request via Tritom.

Note: Data channels are directional and created between two Tritom Applications and Datasets. There can be multiple data channels between same applications, differing by transfer direction and/or Datasets.

### Serving data requests

In case data is shared only on request, two Tritom data channels are needed - one for the data request and another for the response. The chart below demonstrates the messages at both ends of the Tritom data channels.

In this example, the Tritom connector of the data sharing server is set in PUSH mode, so it keeps polling the Tritom service and forwards data requests to the data sending application as soon it receives them.

![Communication between docker containers.](/charts/container_messages.drawio.png)

If the web server is connected to a database, it could compose the dataset dynamically based on the data request details. However, the web server in this repo shares only static data.

**Notes**
- A new data request may arrive while the data sending application is still processing a previous request.
  - Solved by composing and sending the dataset in the background to prevent blocking the web server.
- In PUSH mode, the Tritom connector pushes all data requests one by one to the data sending application. It does not resend them even if the application does not respond. In worst case, a data request is never received.
  - Not solved in this repo. However, the data requester can resend their data request.
  - Consequently, during maintenance breaks, the Tritom connector should be stopped or set to PULL mode. After maintenance, all piled up data requests should be processed at once (they will probably not arrive one by one). This is not implemented in this repo.

Next, continue to instructions how to set up and run a local FastAPI server on Linux to respond to Tritom data requests.

# Prepare data file

Save your data file to ```data/```. Remember that in Tritom demo version the max size of data messages is 5 MB. Data format can be any that can be read as a json object or a string.

Note: A zip file cannot be sent via Tritom. If you need to compress your file (e.g. GeoJSON data), convert it first into a netcdf4 compressed .nc file and finally to base64 encoded .txt file.

# Get a Tritom connector

In Tritom Enterprise demo environment, set up an Application and two Datasets: an inbound Dataset for receiving data requests, and an outbound Dataset for sending data.

Download your Tritom Application's connector image from Tritom.

Load docker image from the .tar file:
```bash
docker load -i <PATH/TO/CONNECTOR/IMAGEFILE.tar>    # Replace with path to the loaded image file
```

Check the name of the loaded image:
```bash
docker image ls

# If you can't find the Tritom connector image on the list, do this:
docker image ls -a    # Check hidden images
docker image tag <IMAGE ID> <NEW IMAGE NAME>:main  # Tag the image
docker image ls       # Now it should show up in the image list
```

# Configure

## Docker-compose.yml
Set the name of the Tritom connector image in ```docker-compose.yml```.
```yml
# docker-compose.yml
services:
  tritom_connector:
    container_name: tritom_connector
    image: <NAME OF THE CONNECTOR IMAGE>:main         # Fill this in!
```

Add names of your Tritom Application and its inbound and outbound Datasets. The web server needs to know these when sending messages via Tritom.
```yml
# docker-compose.yml
  web_server:
    container_name: web_server
    image: web_server:main
    environment:
      - TRITOM_CONNECTOR_API_URL=http://127.0.0.1:8080/messages
      - TRITOM_CONNECTOR_API_KEY=/run/secrets/tritom_connector_api_key
      - TRITOM_APPLICATION_NAME=            # Fill this in
      - TRITOM_DATASET_REQUEST_INBOUND=     # Fill this in
      - TRITOM_DATASET_NAME_OUTBOUND=       # Fill this in
      - DATA_FILE=./data/Test_Data_Product.json   # Replace with your own data file
```

Replace path to the data file, or use the provided example data set ```data/Test_Data_Product.json```.

## Set API key
Run the Tritom connector to find its api key in the log:
```bash
docker compose up tritom_connector
```
Stop running with Ctrl + C. Add the api key to ```.secrets/tritom_connector_api_key.txt```.
```bash
# .secrets/tritom_api_key_sender.txt
"<API KEY OF THE TRITOM CONNECTOR>"
```

# Start sharing data via Tritom

In ```docker-compose.yml``` file, there are three docker containers that are needed for serving data requests: 1) Tritom connector of the data sharing application, 2) web server, and 3) HTTP/2 proxy.

It is often practical to hide the output of the Tritom connector container, because it polls Tritom regularly (in PUSH mode) and fills the terminal with unnecessary messages.

```bash
# Run all containers but hide the output of 'tritom_connector'
docker compose up --no-attach tritom_connector
```

When making changes to the web server, you may want to stop, update and restart only the web_server container, because Tritom connector may be slow to start. You can stop it in another terminal:

```python
# Stop only the web_server container
docker compose down web_server

# Make changes to the server

# Restart it in deattached mode
docker compose up web_server -d --build

# Logging continues in the terminal that's already logging the other running containers.
```

# Testing the data exchange

## Create another Tritom Application

To send a data request and receive data from this web server via Tritom, you need another Tritom Application (Application B in the [figure above](#data-sharing-via-tritom-simplified)). This Application should also have two Datasets (outbound for sending data requests and inbound for receiving data). In Tritom, open data channels to connect them with the corresponding datasets of the web server application.

Download and load the Tritom connector image of this Application (see [Get a Tritom connector](#get-a-tritom-connector)). Set the image name and settings in **docker-compose.yml** file:
```yml
  tritom_connector_data_requester:
    container_name: tritom_connector_data_requester
    image: "<NAME OF CONNECTOR IMAGE>:main"   # Fill this in
    ports:
      - "8888:8080"     # Use a different port from the first Tritom connector
```

## (Re)run all containers
```bash
docker compose up --no-attach tritom_connector
```
Identify the api key of the second Tritom connector (tritom_connector_data_requester).

## Send data request

Now you're ready to simulate data requests coming from any Tritom application.

Use curl in command prompt to send a message to *tritom_connector_data_requester*. Fill in this POST request:
- api key of the Tritom connector (tritom_connector_data_requester),
- Tritom Application names at both ends of the data channel, and
- Dataset name in Tritom.

```bash
curl --http2 --connect-timeout 10 --max-time 10 \
 -H "ClientApiKey: <TRITOM API KEY OF tritom_connector_data_requester>" \
 -H "Content-Type: application/json" -X POST http://127.0.0.1:8888/messages \
 -d '{"originServiceId": "<DATA REQUESTING APPLICATION B>", "dataset": "<OUTBOUND DATASET OF THE REQUESTING APPLICATION>", "body": {}}'
```

## Receive data

If the web server responds by sending a dataset via Tritom, receive the data with this GET request to *tritom_connector_data_requester*:

```bash
curl --http2 --connect-timeout 10 --max-time 10 \
 -H "ClientApiKey: <TRITOM API KEY OF tritom_connector_data_requester>" \
 -H "Content-Type: application/json" \
 -X GET http://127.0.0.1:8888/messages
```

## Stop the containers
When done, stop running with Ctrl + C, or docker compose down.

# Debugging

- Cannot run Tritom connector because image pulling fails?
  - Switch cloud firewall off or allow pulling images from Tritom.
- Tritom connector runs but logs 'Error on push null' when retrieving messages.
  - Switch cloud firewall off or allow requests to Tritom environment.
- web_server sends data to tritom_connector, but tritom_connector_data_requester never receives it.
  - Is there a data channel in Tritom, specifying the correct dataset, Applications and direction of data transfer?
  - Does .secrets/Tritom_api_key.txt contain the api key of tritom_connector?
  - Are you using the correct api key (of tritom_connector_data_requester) in the curl GET request?
