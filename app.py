from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
import boto3
import uuid
import datetime
import os

app = Flask(__name__)
app.secret_key = "super_secret_key_for_flash_messages"

# --- AWS CONFIGURATION ---
REGION = 'us-east-1'
BUCKET_NAME = 'smart-cloud-notes-app' # <--- CHANGE THIS!
DYNAMO_TABLE = 'CloudNotes'

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb', region_name=REGION)
table = dynamodb.Table(DYNAMO_TABLE)
s3_client = boto3.client('s3', region_name=REGION)

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def dashboard():
    # Fetch all notes
    try:
        response = table.scan()
        notes = response.get('Items', [])
        notes.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Extract unique subjects for the sidebar/filter
        subjects = list(set([note.get('subject', 'Uncategorized') for note in notes]))
        subjects.sort()
    except Exception as e:
        print(f"Error: {e}")
        notes = []
        subjects = []
        
    return render_template('dashboard.html', notes=notes, subjects=subjects)

@app.route('/subject/<subject_name>')
def view_subject(subject_name):
    try:
        response = table.scan()
        all_notes = response.get('Items', [])
        # Filter notes by subject
        notes = [n for n in all_notes if n.get('subject') == subject_name]
        notes.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    except Exception as e:
        notes = []
        
    return render_template('subject.html', notes=notes, subject_name=subject_name)

@app.route('/add', methods=['GET', 'POST'])
def add_note():
    if request.method == 'GET':
        return render_template('add_note.html')
        
    title = request.form.get('title')
    subject = request.form.get('subject', 'General').strip().title()
    content = request.form.get('content')
    file = request.files.get('file')
    
    note_id = str(uuid.uuid4())
    created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    file_name = None
    s3_key = None

    # Handle S3 File Upload
    if file and allowed_file(file.filename):
        original_filename = secure_filename(file.filename)
        # Create a unique S3 key to prevent overwriting files with the same name
        s3_key = f"uploads/{note_id}_{original_filename}"
        file_name = original_filename
        
        try:
            s3_client.upload_fileobj(file, BUCKET_NAME, s3_key)
        except Exception as e:
            print(f"S3 Upload Error: {e}")
            flash("Error uploading file to S3.", "error")
            return redirect(url_for('add_note'))

    # Save metadata to DynamoDB
    item = {
        'note_id': note_id,
        'title': title,
        'subject': subject,
        'content': content,
        'created_at': created_at
    }
    
    if s3_key:
        item['file_name'] = file_name
        item['s3_key'] = s3_key

    table.put_item(Item=item)
    return redirect(url_for('dashboard'))

@app.route('/download/<note_id>')
def download_file(note_id):
    # Fetch note details from DynamoDB to get the S3 key
    response = table.get_item(Key={'note_id': note_id})
    note = response.get('Item')
    
    if note and 's3_key' in note:
        # Generate a PRESIGNED URL (Valid for 1 hour)
        # This is a highly secure AWS best practice!
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': note['s3_key']},
            ExpiresIn=3600
        )
        return redirect(presigned_url)
    return "File not found", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
