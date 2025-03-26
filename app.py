from flask import Flask, render_template, jsonify
import pandas as pd
from datetime import datetime
import os
import subprocess
from threading import Thread, Lock
from flask_cors import CORS  # Import CORS

# Initialize Flask app
app = Flask(__name__)

# Configure CORS to allow requests from frontend domains
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "https://jsw-scrapped-data-frontend.vercel.app",
            "http://localhost:3000", 
            "http://127.0.0.1:3000",
            "http://192.168.1.210:3000"
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Add these global variables after the imports
CSV_FILE = "qualified_news.csv"
last_modified_time = 0
cached_projects = []
pipeline_running = False
pipeline_lock = Lock()

def load_projects_from_csv():
    """Load projects from CSV file with caching"""
    global last_modified_time, cached_projects
    
    try:
        # Check if file exists
        if not os.path.exists(CSV_FILE):
            return []
            
        # Get current file modification time
        current_mtime = os.path.getmtime(CSV_FILE)
        
        # If file hasn't changed and we have cached data, return cached data
        if current_mtime == last_modified_time and cached_projects:
            return cached_projects
            
        # Read CSV file with specific column names
        df = pd.read_csv(CSV_FILE)
        
        # Convert DataFrame to list of dictionaries
        projects = df.to_dict('records')
        
        # Update cache
        last_modified_time = current_mtime
        cached_projects = projects
        
        return projects
    except Exception as e:
        print(f"Error loading projects from CSV: {e}")
        return []

def run_pipeline_async():
    """Run the deepseek pipeline in a separate process"""
    global pipeline_running
    try:
        with pipeline_lock:
            pipeline_running = True
        subprocess.run(['python', 'deepseek_pipeline.py'], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Pipeline execution failed: {e}")
    except Exception as e:
        print(f"Error running pipeline: {e}")
    finally:
        with pipeline_lock:
            pipeline_running = False

@app.route('/')
def index():
    """Render the main page"""
    projects = load_projects_from_csv()
    no_projects = len(projects) == 0
    return render_template('index.html', projects=projects, no_projects=no_projects)

@app.route('/api/projects')
def get_projects():
    """API endpoint to get all projects"""
    projects = load_projects_from_csv()
    return jsonify(projects)

@app.route('/api/projects/<int:project_id>')
def get_project(project_id):
    """API endpoint to get a specific project"""
    projects = load_projects_from_csv()
    if 0 <= project_id < len(projects):
        return jsonify(projects[project_id])
    return "Project not found", 404

@app.route('/api/run_pipeline', methods=['POST'])
def run_pipeline():
    """API endpoint to start the pipeline"""
    global pipeline_running
    try:
        with pipeline_lock:
            if pipeline_running:
                return jsonify({"status": "error", "message": "Pipeline is already running"}), 400
            pipeline_running = True
        
        # Start the pipeline in a separate thread
        thread = Thread(target=run_pipeline_async)
        thread.daemon = True
        thread.start()
        return jsonify({"status": "success", "message": "Pipeline started successfully"})
    except Exception as e:
        with pipeline_lock:
            pipeline_running = False
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/pipeline_status')
def get_pipeline_status():
    """API endpoint to check pipeline status"""
    with pipeline_lock:
        return jsonify({"running": pipeline_running})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # Default to 5000 if PORT is not set
    app.run(host='0.0.0.0', port=port, debug=True) 