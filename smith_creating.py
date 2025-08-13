from dotenv import load_dotenv, find_dotenv
import os
from langsmith import Client
import uuid

load_dotenv(find_dotenv())
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"

client = Client()

PROJECT_NAME = f"abar"
session = client.create_project(
    project_name=PROJECT_NAME,
    description="This is a project for Abar"
)
