"""Small dependency-free, valid one-page PDF fixtures, visibly marked as samples."""

def sample_pdf(lines):
    def escape(value):
        return str(value).encode('ascii', 'replace').decode('ascii').replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    commands = ['BT /F1 14 Tf 50 790 Td (DEMO SAMPLE - NOT A REAL BUSINESS DOCUMENT) Tj', '/F1 11 Tf']
    for line in lines:
        commands.append('0 -24 Td (%s) Tj' % escape(line))
    commands.append('ET')
    stream = '\n'.join(commands).encode('ascii')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length %d >>\nstream\n' % len(stream) + stream + b'\nendstream']
    result = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(('%d 0 obj\n' % i).encode() + obj + b'\nendobj\n')
    xref = len(result)
    result.extend(b'xref\n0 6\n0000000000 65535 f \n')
    for offset in offsets[1:]:
        result.extend(('%010d 00000 n \n' % offset).encode())
    result.extend(('trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % xref).encode())
    return bytes(result)
