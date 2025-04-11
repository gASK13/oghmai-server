@echo off

:: Create the necessary directories
if not exist layers\oghmai_layer\python md layers\oghmai_layer\python

:: Install dependencies into the target directory
py -m pip install -r lambda\requirements.txt -t layers\oghmai_layer\python

:: Zip the contents of the python folder
powershell -Command "Compress-Archive -Path layers\oghmai_layer\python\* -DestinationPath layers\oghmai_layer.zip -Force"

:: Generate the OpenAPI schema
py lambda\openapi.py

:: Move the generated openapi.yaml to the infra folder
move /Y openapi.yaml infra\

echo Deployment package and OpenAPI schema have been created and moved.