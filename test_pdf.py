from fpdf import FPDF
import io
import os

def test_pdf():
    try:
        pdf = FPDF()
        pdf.add_page()
        # Try Arial first
        try:
            pdf.set_font("Arial", 'B', 14)
            print("Arial works")
        except Exception as e:
            print(f"Arial failed: {e}")
            pdf.set_font("helvetica", 'B', 14)
            print("helvetica works as fallback")
            
        pdf.cell(0, 10, "Test PDF", ln=True)
        
        output = io.BytesIO()
        # Test both ways
        try:
            pdf_content = pdf.output(dest='S')
            print(f"pdf.output(dest='S') returned type: {type(pdf_content)}")
        except Exception as e:
            print(f"pdf.output(dest='S') failed: {e}")
            pdf_content = pdf.output()
            print(f"pdf.output() returned type: {type(pdf_content)}")
            
        output.write(pdf_content)
        print("Successfully wrote to BytesIO")
        return True
    except Exception as e:
        print(f"Overall PDF generation failed: {e}")
        return False

if __name__ == "__main__":
    test_pdf()
