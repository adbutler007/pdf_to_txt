import base64
import requests
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
import io
import os
import glob

api_key = os.environ.get("OPENAI_API_KEY")

path = "char_sheets/Adbutler007_93789931 (2).pdf"

# instructions = """The high resolution image is a page of a DnD Beyond pdf character sheet.
#                 Take great care to render all the text on the page using markdown tables to best approximate the structure of the original pdf.
#                 Always ONLY render the character sheet and never append or prepend descriptive text, ticks, apostrophes, or quotation marks.
#                 """

instructions = """The high resolution image is a page of a DnD Beyond pdf character sheet.
                Take great care to render all the information on the page using an optimal structure for human interpretation. Use markdown style tables for optimal human readability on a letter sized and oriented screen. Pay exhaustive attention to optimal design and alignment of tables and columns. Only render alphanumeric and formatting characters like | or * but never employ special characters like ☐.
                Always ONLY render the character sheet content and NEVER append or prepend descriptive text, ticks, apostrophes, or quotation marks. Always ONLY render the character sheet content and NEVER append or prepend descriptive text, ticks, apostrophes, or quotation marks.
                """

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

headers = {
  "Content-Type": "application/json",
  "Authorization": f"Bearer {api_key}"
}

pdf_files = glob.glob("./char_sheets/*.pdf")

for pdf_file in pdf_files:
    # Initialize markdown content
    markdown_content = ""

    for payload in pdf_to_payload(pdf_file):
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response_json = response.json()
        markdown_content += response_json['choices'][0]['message']['content']
        markdown_content += "\n---\n"  # Append a page break

    # Save the markdown content to a file
    output_file = f"./output/{os.path.splitext(os.path.basename(pdf_file))[0]}.txt"
    with open(output_file, 'w') as f:
        f.write(markdown_content)