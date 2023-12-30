from fastapi import FastAPI, UploadFile, File, Response
from fastapi.responses import HTMLResponse, FileResponse
from pdf2image import convert_from_bytes
import base64
import requests
import io
import os
import glob
import shutil
from typing import List
import httpx
import asyncio

app = FastAPI()

@app.get("/")
def read_root():
    with open("index.html", 'r') as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, status_code=200)

api_key = os.environ.get("OPENAI_API_KEY")

instructions = """The high resolution image is a page of a DnD Beyond pdf character sheet.
                Take great care to render all the information on the page using an optimal structure for human interpretation. Use markdown style tables for optimal human readability on a letter sized and oriented screen. Pay attention to optimal design and alignment of columns.
                Always ONLY render the character sheet content and NEVER append or prepend descriptive text, ticks, apostrophes, or quotation marks. Always ONLY render the character sheet content and NEVER append or prepend descriptive text, ticks, apostrophes, or quotation marks.
                """

headers = {
  "Content-Type": "application/json",
  "Authorization": f"Bearer {api_key}"
}

from pdf2image import convert_from_bytes

import httpx
import asyncio

async def pdf_to_payload(pdf_file):
    # Read the PDF file
    pdf_data = pdf_file.read()

    # Convert each page to an image
    images = convert_from_bytes(pdf_data, dpi=600)

    # Initialize a dictionary to store the responses
    responses = {}

    # Process each image
    for i, image in enumerate(images):
        # Convert image to base64
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        base64_image = base64.b64encode(buffered.getvalue()).decode()

        # Initialize the message content list
        message_content = [
            {
                "type": "text",
                "text": instructions,
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            }
        ]

        # Construct the payload
        payload = {
            "model": "gpt-4-vision-preview",
            "messages": [
                {
                    "role": "user",
                    "content": message_content
                }
            ],
            "max_tokens": 4000
        }

        # Make the request
        async with httpx.AsyncClient() as client:
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response_json = response.json()

        # Store the response in the dictionary
        responses[i] = response_json['choices'][0]['message']['content']

    # Yield the responses in order
    for i in sorted(responses):
        yield responses[i]

@app.post("/convert_single/")
async def convert_single(file: UploadFile = File(...)):
    # Initialize markdown content
    markdown_content = ""

    for payload in pdf_to_payload(file.file):
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response_json = response.json()
        markdown_content += response_json['choices'][0]['message']['content']
        markdown_content += "\n---\n"  # Append a page break

    # Save the markdown content to a file in the ./tmp directory
    output_file = f"./tmp/{os.path.splitext(file.filename)[0]}.txt"
    with open(output_file, 'w') as f:
        f.write(markdown_content)

    return FileResponse(output_file, media_type="text/plain")

import os

@app.post("/convert_multiple/")
async def convert_multiple(files: List[UploadFile] = File(...)):
    # Create a subdirectory in ./tmp for the text files
    os.makedirs("./tmp/txt", exist_ok=True)

    # Initialize a list to store the images and their associated filenames
    images = []

    # Convert all PDFs to images
    for file in files:
        print(f"Processing file: {file.filename}")

        # Read the PDF file
        pdf_data = file.file.read()

        # Convert each page to an image and store it in the list
        for image in convert_from_bytes(pdf_data, dpi=600):
            images.append((file.filename, image))

    # Initialize a dictionary to store the responses
    responses = {}

    # Process each image
    for i, (filename, image) in enumerate(images):
        # Convert image to base64
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        base64_image = base64.b64encode(buffered.getvalue()).decode()

        # Initialize the message content list
        message_content = [
            {
                "type": "text",
                "text": instructions,
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            }
        ]

        # Construct the payload
        payload = {
            "model": "gpt-4-vision-preview",
            "messages": [
                {
                    "role": "user",
                    "content": message_content
                }
            ],
            "max_tokens": 4000
        }

        # Make the request
        async with httpx.AsyncClient() as client:
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response_json = response.json()

        # Store the response in the dictionary
        responses[(filename, i)] = response_json['choices'][0]['message']['content']

    # Initialize a dictionary to store the markdown content for each file
    markdown_contents = {}

    # Aggregate the responses into individual text documents
    for (filename, i), content in sorted(responses.items(), key=lambda x: (x[0][0], x[0][1])):
        if filename not in markdown_contents:
            markdown_contents[filename] = ""
        markdown_contents[filename] += content
        markdown_contents[filename] += "\n---\n"  # Append a page break

    # Save the markdown content to a file in the ./tmp/txt directory for each file
    for filename, markdown_content in markdown_contents.items():
        output_file = f"./tmp/txt/{os.path.splitext(filename)[0]}.txt"
        with open(output_file, 'w') as f:
            f.write(markdown_content)

    # Zip the ./tmp/txt directory
    zip_file = shutil.make_archive("./tmp/output", 'zip', "./tmp/txt")
    print(f"Created zip file: {zip_file}")

    # Delete all files in the ./tmp/txt directory
    files = glob.glob('./tmp/txt/*')
    for f in files:
        os.remove(f)

    return FileResponse(zip_file, media_type="application/zip")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)