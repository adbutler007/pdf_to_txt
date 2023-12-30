from fastapi import FastAPI, UploadFile, File, Response
from fastapi.responses import HTMLResponse, FileResponse
from pdf2image import convert_from_bytes
import base64
import io
import os
import glob
import shutil
from typing import List
import httpx
import asyncio
import aiofiles

app = FastAPI()

# Load API key from environment variable
api_key = os.environ.get("OPENAI_API_KEY")

# API headers
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}

# Instructions for API requests
instructions = """The high resolution image is a page of a DnD Beyond pdf character sheet.
                Take great care to render all the information on the page using an optimal structure for human interpretation. Use markdown style tables for optimal human readability on a letter sized and oriented screen. Pay exhaustive attention to optimal design and alignment of tables and columns. Only render alphanumeric and formatting characters like | or * but never employ special characters like ☐.
                Always ONLY render the character sheet content and NEVER append or prepend descriptive text, ticks, apostrophes, or quotation marks. Always ONLY render the character sheet content and NEVER append or prepend descriptive text, ticks, apostrophes, or quotation marks."""

@app.get("/")
async def read_root():
    async with aiofiles.open("index.html", 'r') as f:
        html_content = await f.read()
    return HTMLResponse(content=html_content, status_code=200)

async def process_image(image, dpi=300):
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG")
    base64_image = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/jpeg;base64,{base64_image}"

async def make_api_request(base64_image):
    message_content = [
        {"type": "text", "text": instructions},
        {"type": "image_url", "image_url": {"url": base64_image}}
    ]

    payload = {
        "model": "gpt-4-vision-preview",
        "messages": [{"role": "user", "content": message_content}],
        "max_tokens": 4000
    }

    try:
        async with httpx.AsyncClient(timeout=2400.0) as client:  # Increased timeout
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response_json = response.json()
            return response_json['choices'][0]['message']['content']
    except httpx.ReadTimeout:
        # Handle the timeout, e.g., retry, return an error message, etc.
        return "Request timed out. Please try again."


@app.post("/convert_single/")
async def convert_single(file: UploadFile = File(...)):
    markdown_content = ""
    pdf_data = await file.read()

    images = convert_from_bytes(pdf_data, dpi=300)  # Reduced DPI for efficiency
    for image in images:
        base64_image = await process_image(image)
        response_content = await make_api_request(base64_image)
        markdown_content += response_content + "\n---\n"

    output_file = f"./tmp/{os.path.splitext(file.filename)[0]}.txt"
    async with aiofiles.open(output_file, 'w') as f:
        await f.write(markdown_content)

    return FileResponse(output_file, media_type="text/plain")

@app.post("/convert_multiple/")
async def convert_multiple(files: List[UploadFile] = File(...)):
    os.makedirs("./tmp/txt", exist_ok=True)
    markdown_contents = {}
    for file in files:
        filename = os.path.splitext(file.filename)[0]
        markdown_contents[filename] = ""

        pdf_data = await file.read()
        images = convert_from_bytes(pdf_data, dpi=300)  # Reduced DPI for efficiency

        for image in images:
            base64_image = await process_image(image)
            response_content = await make_api_request(base64_image)
            markdown_contents[filename] += response_content + "\n---\n"

    for filename, markdown_content in markdown_contents.items():
        output_file = f"./tmp/txt/{filename}.txt"
        async with aiofiles.open(output_file, 'w') as f:
            await f.write(markdown_content)

    zip_file = shutil.make_archive("./tmp/output", 'zip', "./tmp/txt")

    # Cleanup
    for f in glob.glob('./tmp/txt/*'):
        os.remove(f)

    return FileResponse(zip_file, media_type="application/zip")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
