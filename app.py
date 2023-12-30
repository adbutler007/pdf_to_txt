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

def pdf_to_payload(pdf_file):
    # Read the PDF file
    pdf_data = pdf_file.read()

    # Convert each page to an image
    images = convert_from_bytes(pdf_data, dpi=600)

    # Process each image
    for image in images:
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

        yield payload

@app.post("/convert_single/")
async def convert_single(file: UploadFile = File(...)):
    # Initialize markdown content
    markdown_content = ""

    for payload in pdf_to_payload(file.file):
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response_json = response.json()
        markdown_content += response_json['choices'][0]['message']['content']
        markdown_content += "\n---\n"  # Append a page break

    # Save the markdown content to a file
    output_file = f"./output/{os.path.splitext(file.filename)[0]}.txt"
    with open(output_file, 'w') as f:
        f.write(markdown_content)

    return FileResponse(output_file, media_type="text/plain")

@app.post("/convert_multiple/")
async def convert_multiple(files: List[UploadFile] = File(...)):
    for file in files:
        print(f"Processing file: {file.filename}")

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

        print(f"Successfully processed file: {file.filename}")

    # Zip the ./tmp directory
    shutil.make_archive("./tmp/output", 'zip', "./tmp")

    # Delete all files in the ./tmp directory
    files = glob.glob('./tmp/*')
    for f in files:
        os.remove(f)

    return FileResponse("./tmp/output.zip", media_type="application/zip")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True, timout = 1200)