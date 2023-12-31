from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from datetime import datetime
from pdf2image import convert_from_bytes
from collections import defaultdict
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


async def chat_completion(draft_char_sheet):
    with open('formatting_prompt.txt', 'r') as file:
        prompt = file.read()

    prompt = prompt + "\n\n" + draft_char_sheet

    messages = [
        {"role": "system", "content": "You are a Dungeons and Dragons character sheet optimizer."},
        {"role": "user", "content": prompt},
    ]

    payload = {
        "model": "gpt-4-1106-preview",
        "messages": messages
    }

    async with httpx.AsyncClient(timeout=2400.0) as client:  # Increased timeout
        response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response_dict = response.json()
        response_out = response_dict['choices'][0]['message']['content']
        return response_out

@app.post("/convert_multiple/")
async def convert_multiple(files: List[UploadFile] = File(...)):
    print(f"Received {len(files)} files for conversion.")
    # Create a subdirectory in ./tmp for the text files
    os.makedirs("./tmp/txt", exist_ok=True)
    
    # Initialize a list to store the images and their associated filenames
    images = []
    print("Starting pdf-to-image conversions.")
    # Convert all PDFs to images
    for file in files:
        print(f"Processing file: {file.filename}")

        # Read the PDF file
        pdf_data = await file.read()

        # Convert each page to an image and store it in the list
        for image in convert_from_bytes(pdf_data, dpi=300):
            images.append((file.filename, image))

    print(f"Converted all PDFs to images. Total images: {len(images)}")

    # Initialize a dictionary to store the responses
    responses = {}

    # Process each image
    tasks = []
    async with httpx.AsyncClient(timeout=2400.0) as client:
        for i, (filename, image) in enumerate(images):
            print(f"Processing image {i+1} of {len(images)} from file: {filename}")

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
            tasks.append(client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload))

        # Wait for all tasks to complete
        responses_raw = await asyncio.gather(*tasks)

        # Process the responses
        for i, response in enumerate(responses_raw):
            response_json = response.json()
            if images[i][0] in responses:
                responses[images[i][0]] += response_json['choices'][0]['message']['content']
            else:
                responses[images[i][0]] = response_json['choices'][0]['message']['content']

    print("Processed all images.")

    # Initialize a dictionary to store the markdown content for each file
    markdown_contents = defaultdict(str)

    # Aggregate the responses into individual text documents
    for filename, content in responses.items():
        markdown_contents[filename] += content
        markdown_contents[filename] += "\n---\n"  # Append a page break

    print("Aggregated all responses into individual text documents.")

    # Save the markdown content to a file in the ./tmp/txt directory for each file
    tasks = []
    for filename, markdown_content in markdown_contents.items():
        # Get current date and time
        now = datetime.now()
        # Format as a string
        now_str = now.strftime("%Y-%m-%d_%H-%M-%S")
        # Append date and time to content
        markdown_content += f"\n\nDate and Time: {now_str}"
        output_file = f"./tmp/txt/{os.path.splitext(filename)[0]}.txt"
        with open(output_file, 'w') as f:
            f.write(markdown_content)

        print(f"Saved markdown content to file: {output_file}")

        # Call chat_completion on the final assembled text
        tasks.append(chat_completion(markdown_content))

    # Wait for all tasks to complete
    optimized_contents = await asyncio.gather(*tasks)

    # Write the optimized content to the files
    for filename, optimized_content in zip(markdown_contents.keys(), optimized_contents):
        output_file = f"./tmp/txt/{os.path.splitext(filename)[0]}.txt"
        with open(output_file, 'w') as f:
            f.write(optimized_content)

    print("Optimized character sheet output.")

    # Zip the ./tmp/txt directory
    zip_file = shutil.make_archive("./tmp/output", 'zip', "./tmp/txt")
    print(f"Created zip file: {zip_file}")

    # Delete all files in the ./tmp/txt directory
    files = glob.glob('./tmp/txt/*')
    for f in files:
        os.remove(f)

    print("Deleted all files in the ./tmp/txt directory.")

    return FileResponse(zip_file, media_type="application/zip")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
