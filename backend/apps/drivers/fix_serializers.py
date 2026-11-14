with open('apps/drivers/serializers.py', 'r') as f:
    content = f.read()

old = '''    def get_documents(self, obj):
        """Return list of documents for this driver"""
        docs = Document.objects.filter(driver=obj, status='active')
        return [
            {
                "id": doc.id,
                "document_name": doc.document_name,
                "original_filename": doc.original_filename,
                "file_size_mb": round(doc.file_size / 1024 / 1024, 2) if doc.file_size else 0,
                "upload_date": doc.upload_date,
                "description": doc.description,
            }
            for doc in docs
        ]
'''

new = '''    def get_documents(self, obj):
        """Return list of documents for this driver"""
        docs = Document.objects.filter(driver=obj, status='active')
        return [
            {
                "id": doc.id,
                "document_name": doc.document_name,
                "original_filename": doc.original_filename,
                "file_size_mb": round(doc.file_size / 1024 / 1024, 2) if doc.file_size else 0,
                "upload_date": doc.upload_date,
                "description": doc.description,
            }
            for doc in docs
        ]
'''

if old in content:
    content = content.replace(old, new)
    with open('apps/drivers/serializers.py', 'w') as f:
        f.write(content)
    print('SUCCESS: Replacement made')
else:
    print('ERROR: oldString not found')
    lines = content.split('\n')
    for i, line in enumerate(lines[346:360], start=347):
        print(f'{i}: {line!r}')