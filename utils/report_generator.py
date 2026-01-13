# -*- coding: utf-8 -*-
from fpdf import FPDF
from datetime import datetime
import os

class PDF(FPDF):
    def header(self):

        self.set_font('Arial', 'B', 15)

        self.cell(0, 10, 'Missing Person Trace Report', 0, 1, 'C')
        self.ln(5)

    def footer(self):

        self.set_y(-15)

        self.set_font('Arial', 'I', 8)

        self.cell(0, 10, 'Page ' + str(self.page_no()) + '/{nb}', 0, 0, 'C')
        self.cell(0, 10, f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 0, 'R')

def generate_case_report(case_data, updates, upload_folder):
    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.add_page()


    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, f"Case Information - Ticket ID: {case_data['ticket_id']}", 0, 1, 'L')
    pdf.ln(5)


    if case_data.get('photo_path'):
        photo_path = os.path.join(upload_folder, case_data['photo_path'])
        if os.path.exists(photo_path):

            try:
                pdf.image(photo_path, x=150, y=30, w=40)
            except Exception as e:
                print(f"Could not load image for PDF: {e}")

    pdf.set_font('Arial', '', 10)



    pdf.cell(40, 8, "Full Name:", 0, 0)
    pdf.cell(100, 8, f"{case_data.get('full_name', 'N/A')}", 0, 1)

    pdf.cell(40, 8, "Status:", 0, 0)
    pdf.set_font('Arial', 'B', 10)
    status = case_data.get('status', 'Unknown')

    pdf.cell(100, 8, status, 0, 1)
    pdf.set_font('Arial', '', 10)

    pdf.cell(40, 8, "Age / Gender:", 0, 0)
    pdf.cell(100, 8, f"{case_data.get('age', 'N/A')} / {case_data.get('gender', 'N/A')}", 0, 1)

    pdf.cell(40, 8, "Last Seen Date:", 0, 0)
    pdf.cell(100, 8, f"{case_data.get('last_seen_date', 'N/A')}", 0, 1)

    pdf.cell(40, 8, "Location:", 0, 0)
    pdf.multi_cell(90, 8, f"{case_data.get('last_seen_location', 'N/A')}")

    pdf.cell(40, 8, "Contact:", 0, 0)
    pdf.cell(100, 8, f"{case_data.get('contact_phone', 'N/A')}", 0, 1)

    pdf.ln(5)
    pdf.cell(40, 8, "Description:", 0, 0)
    pdf.ln(8)
    pdf.multi_cell(0, 6, f"{case_data.get('description', 'N/A')}")

    pdf.ln(10)


    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Case Updates / Detection Log', 0, 1, 'L')
    pdf.set_font('Arial', '', 9)


    pdf.set_fill_color(200, 220, 255)
    pdf.cell(40, 8, 'Date/Time', 1, 0, 'C', True)
    pdf.cell(40, 8, 'Type', 1, 0, 'C', True)
    pdf.cell(110, 8, 'Details', 1, 1, 'C', True)

    if updates:
        for update in updates:

            ts = update.get('created_at')
            date_str = ts.strftime('%Y-%m-%d %H:%M') if ts else "N/A"

            pdf.cell(40, 8, date_str, 1, 0, 'C')
            pdf.cell(40, 8, update.get('update_type', 'N/A'), 1, 0, 'C')


            x = pdf.get_x()
            y = pdf.get_y()


            pdf.multi_cell(110, 8, update.get('details', 'N/A'), border=1)










    else:
        pdf.cell(190, 8, "No updates recorded.", 1, 1, 'C')







    filename = f"report_{case_data['ticket_id']}.pdf"
    output_path = os.path.join(upload_folder, filename)
    pdf.output(output_path)
    return filename
