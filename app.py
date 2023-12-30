from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
from PyPDF2 import PdfReader
from pdf2image import convert_from_path
import base64
import requests
import io
import os
import glob
import shutil

app = FastAPI()

api_key = os.environ.get("OPENAI_API_KEY")

instructions = """The high resolution image is a page of a DnD Beyond pdf character sheet.
                Take great care to render all the information on the page using an optimal structure for human interpretation. Use markdown style tables for optimal human readability on a letter sized and oriented screen. Pay attention to optimal design and alignment of columns.
                Always ONLY render the character sheet content and NEVER append or prepend descriptive text, ticks, apostrophes, or quotation marks. Always ONLY render the character sheet content and NEVER append or prepend descriptive text, ticks, apostrophes, or quotation marks.
                """

headers = {
  "Content-Type": "application/json",
  "Authorization": f"Bearer {api_key}"
}

def pdf_to_payload(pdf_path):
    # Read the PDF file
    pdf = PdfReader(open(pdf_path, "rb"))

    # Convert each page to an image
    images = convert_from_path(pdf_path, dpi=600)

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

@app.get("/convert_directory/{input_dir}")
async def convert_directory(input_dir: str):
    # Get all PDF files in the input directory
    pdf_files = glob.glob(f"./{input_dir}/*.pdf")

    for pdf_file in pdf_files:
        # Initialize markdown content
        markdown_content = ""

        for payload in pdf_to_payload(pdf_file):
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response_json = response.json()
            markdown_content += response_json['choices'][0]['message']['content']
            markdown_content += "\n---\n"  # Append a page break

        # Save the markdown content to a file in the ./tmp directory
        output_file = f"./tmp/{os.path.splitext(os.path.basename(pdf_file))[0]}.txt"
        with open(output_file, 'w') as f:
            f.write(markdown_content)

    # Zip the ./tmp directory
    shutil.make_archive("./tmp/output", 'zip', "./tmp")

    return FileResponse("./tmp/output.zip", media_type="application/zip")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)