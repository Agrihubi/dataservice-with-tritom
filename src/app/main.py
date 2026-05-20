"""
Web server that listens to data requests and sends a static dataset to the
requester via Tritom.
"""

from contextlib import asynccontextmanager
import json
import logging
import os
import sys
import types

from dotenv import load_dotenv
from fastapi import FastAPI, Request, BackgroundTasks, status, HTTPException
import httpx

load_dotenv(override=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Sets up static data, connector URL and an AsyncClient for sending data."""

    # Read data file
    datapath = os.environ["DATA_FILE"]
    logger.info("Reading dataset from %s.", datapath)
    dataset = ""
    if datapath.endswith("json", -4):
        with open(datapath, "rt", encoding="UTF-8") as jsonfile:
            dataset = json.load(jsonfile)
    else:
        with open(datapath, "rt", encoding="UTF-8") as file:
            dataset = file.read()
    app.data = dataset
    if len(dataset) > 0:
        logger.info("Dataset read successfully.")
    else:
        logger.warning("Dataset is empty.")

    app.requests_client = httpx.AsyncClient(http2=True)
    app.connector_url = os.environ["TRITOM_CONNECTOR_API_URL"]
    app.ClientApiKeySend = os.environ["TRITOM_CONNECTOR_API_KEY"]

    app.tritom_application = os.environ["TRITOM_APPLICATION_NAME"]
    app.inbound_data_request = os.environ["TRITOM_DATASET_REQUEST_INBOUND"]
    app.outbound_dataset = os.environ["TRITOM_DATASET_NAME_OUTBOUND"]

    yield
    await app.requests_client.aclose()
    app.data = ""

app = FastAPI(version="0.1.0", lifespan=lifespan)

logger = logging.getLogger("hypercorn")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)


@app.middleware("http")
async def log_requests(request: Request, call_next: types.FunctionType) -> str:
    """Logs incoming http requests."""

    logger.debug("Incoming request %s %s", request.method, request.url)
    logger.debug("with headers %s", request.headers)
    request_body = await request.json()
    logger.debug("and body %s", request_body)

    response = await call_next(request)
    logger.debug("Responded status code %s to the data request.",
                 response.status_code)
    return response


@app.post("/incoming-message", status_code=status.HTTP_202_ACCEPTED)
async def handle_incoming_message(request: Request,
                                  background_tasks: BackgroundTasks) -> None:
    """Identify the Tritom data channel where message is coming from, and process it accordingly.

    NOTE: Assumes that messages are received one by one from a Tritom connector in PUSH mode.
    """

    incoming_message = await request.json()
    incoming_message = json.loads(incoming_message)
    try:
        service_id = incoming_message["originServiceId"]
        dataset_name = incoming_message["dataset_name"]
    except (TypeError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Please specify Tritom application and dataset.") from exc

    # TODO: Process incoming messages here
    # Currently, the server just sends a static dataset to the requester
    if dataset_name == app.inbound_data_request:
        background_tasks.add_task(send_data, service_id)
    return


async def send_data(recipient_service: str) -> None:
    """Sends a static dataset to Tritom connector."""

    message_json = {
        "originServiceId": app.tritom_application,
        "recipientServiceId": recipient_service,
        "dataset": app.outbound_dataset,
        "body": app.data
    }
    message_str = json.dumps(message_json)

    headers = {'Content-Type': 'application/json',
               'ClientApiKey': app.ClientApiKeySend}
    logger.info("Sending dataset %s to %s.", app.outbound_dataset, recipient_service)

    requests_client = app.requests_client
    response = await requests_client.post(url=app.connector_url, headers=headers, data=message_str)
    logger.debug("Tritom connector responded %s.", response.status_code)
    return
