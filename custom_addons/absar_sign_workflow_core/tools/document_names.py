"""Sign title formatting shared by the service and offline regression checks."""
def signing_title(source_model, document_label, filename):
    if source_model == 'purchase.order' and str(document_label).strip().upper() == 'PO':
        return filename
    return f'{document_label} - {filename}'
