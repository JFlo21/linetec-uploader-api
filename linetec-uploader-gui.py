import tkinter as tk
from tkinter import filedialog, messagebox
import requests
import pymupdf as fitz  # Requires: pip install pymupdf
import re
import os

# --- CONFIGURATION: Enter on-site server address here ---
API_URL = "http://127.0.0.1:10000/upload"
# -------------------------------------------------------------

def is_valid_cu_code(code):
    """Validates the format of a CU code."""
    # This regex ensures the code starts with 2-5 capital letters, followed by a hyphen,
    # and then one or more word characters (letters, numbers, underscore) or hyphens.
    return bool(re.match(r"^[A-Z]{2,5}-[\w\-]+$", code))

def extract_data_from_pdf(pdf_path, project_id):
    """
    Parses the PDF file to extract structured data.
    NOTE: This parsing method is highly dependent on the exact text layout of the PDF.
    Changes to the PDF's formatting could break this logic.
    """
    final_rows = []
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        messagebox.showerror("PDF Error", f"Could not open or read the PDF file.\nError: {e}")
        return []

    for page_num, page in enumerate(doc):
        # Using get_text("blocks") is more robust than splitting by newline.
        # It provides text with its coordinates, but for this fix, we'll stick to the original logic.
        full_text = page.get_text()
        lines = full_text.split("\n")

        # --- Data Extraction using Regular Expressions ---
        # This is more reliable than assuming data is on a fixed line number.
        work_order_match = re.search(r"Work Order:\s*([A-Z0-9]+)", full_text)
        work_order = work_order_match.group(1) if work_order_match else ""

        location_id_match = re.search(r"Point:\s*(\d+)", full_text)
        location_id = f"Point {int(location_id_match.group(1)):02d}" if location_id_match else ""
        
        work_request_match = re.search(r"Work Req:\s*(.*)", full_text)
        work_request = work_request_match.group(1).strip() if work_request_match else ""

        district_match = re.search(r"District:\s*(.*)", full_text)
        district = district_match.group(1).strip() if district_match else ""

        # --- Main Data Table Parsing ---
        # This section is very fragile. It assumes a fixed number of lines between data points.
        in_cu_section = False
        for i in range(len(lines)):
            line = lines[i].strip()
            if "Capital Installs, Removals, and Transfers" in line:
                in_cu_section = True
                continue
            if in_cu_section and line == "":
                # This logic assumes a blank line marks the end of the section.
                in_cu_section = False
                continue
            if not in_cu_section:
                continue

            # This block is the most likely to fail if PDF layout changes.
            # It checks if the next 5 lines fit a specific pattern.
            try:
                if (i + 6 < len(lines) and
                    re.match(r"^\d+$", lines[i].strip()) and
                    re.match(r"^\d+$", lines[i+1].strip()) and
                    re.match(r"^\d+$", lines[i+2].strip()) and
                    re.match(r"^\d+$", lines[i+3].strip()) and
                    re.match(r"^[A-Z]$", lines[i+4].strip())):

                    inst, rem, tran, aban = map(int, [lines[i], lines[i+1], lines[i+2], lines[i+3]])
                    description = lines[i+5].strip()
                    code_line = lines[i+6].strip()
                    
                    # Find a valid CU code in the line.
                    code_match = re.search(r"([A-Z]{2,5}-[\w\-]+)$", code_line)
                    cu_code = ""
                    if code_match and is_valid_cu_code(code_match.group(1)):
                        cu_code = code_match.group(1)
                    
                    if not cu_code: continue

                    # Create a record for each non-zero quantity.
                    for work_type, quantity in {"Inst": inst, "Rem": rem, "Tran": tran, "Aban": aban}.items():
                        if quantity > 0:
                            final_rows.append({
                                "Project ID": project_id, "Work Type": work_type,
                                "Quantity": quantity, "Description": description,
                                "CU Code": cu_code, "Location ID": location_id,
                                "Work Order #": work_order, "Work Request #": work_request,
                                "District": district
                            })
            except (ValueError, IndexError):
                # This will catch errors if the lines aren't numbers or are out of bounds.
                continue
    return final_rows

def upload_data(data):
    """Sends the extracted data to the server."""
    try:
        res = requests.post(API_URL, json=data, timeout=30)
        res.raise_for_status()  # Raises an exception for bad status codes (4xx or 5xx)
        
        messagebox.showinfo("Success", f"Successfully uploaded {len(data)} records!")

    except requests.exceptions.HTTPError as e:
        messagebox.showerror("Upload Failed", f"Server responded with an error: {e.response.status_code}\n{e.response.text}")
    except requests.exceptions.RequestException as e:
        messagebox.showerror("Connection Error", f"Could not connect to the server at {API_URL}.\n"
                             f"Please ensure the server is running and the address is correct.\n\nError: {e}")
    except Exception as e:
        messagebox.showerror("An Unexpected Error Occurred", str(e))

def browse_pdf():
    """Opens a file dialog to select a PDF."""
    file_path = filedialog.askopenfilename(
        title="Select a PDF file",
        filetypes=[("PDF files", "*.pdf")]
    )
    if file_path:
        pdf_path_var.set(file_path)

def process_and_upload():
    """Main function to orchestrate the PDF processing and upload."""
    pdf_path = pdf_path_var.get().strip()
    proj_id = project_id_var.get().strip()

    if not pdf_path or not os.path.isfile(pdf_path):
        messagebox.showwarning("Input Error", "Please select a valid PDF file.")
        return
    if not proj_id:
        messagebox.showwarning("Input Error", "Please enter a Project ID.")
        return

    # Set a busy cursor
    root.config(cursor="watch")
    root.update()

    data = extract_data_from_pdf(pdf_path, proj_id)
    
    # Revert cursor
    root.config(cursor="")

    if not data:
        messagebox.showinfo("No Data", "No valid data could be extracted from the PDF.")
        return

    upload_data(data)

# --- GUI Setup ---
root = tk.Tk()
root.title("Linetec PDF Uploader")
root.geometry("550x220")
root.resizable(False, False)
root.configure(bg="#f0f0f0")

main_frame = tk.Frame(root, padx=15, pady=15, bg="#f0f0f0")
main_frame.pack(fill="both", expand=True)

# PDF File Row
tk.Label(main_frame, text="PDF File:", bg="#f0f0f0").grid(row=0, column=0, padx=5, pady=10, sticky="e")
pdf_path_var = tk.StringVar()
tk.Entry(main_frame, textvariable=pdf_path_var, width=50).grid(row=0, column=1, padx=5, pady=10)
tk.Button(main_frame, text="Browse...", command=browse_pdf).grid(row=0, column=2, padx=5, pady=10)

# Project ID Row
tk.Label(main_frame, text="Project ID:", bg="#f0f0f0").grid(row=1, column=0, padx=5, pady=10, sticky="e")
project_id_var = tk.StringVar()
tk.Entry(main_frame, textvariable=project_id_var, width=25).grid(row=1, column=1, padx=5, pady=10, sticky="w")

# Upload Button
upload_button = tk.Button(
    main_frame,
    text="Process and Upload",
    command=process_and_upload,
    bg="#4CAF50",
    fg="white",
    font=("Arial", 10, "bold"),
    padx=10,
    pady=5
)
upload_button.grid(row=2, column=1, pady=20)

root.mainloop()
