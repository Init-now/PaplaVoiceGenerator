from flask import Flask, render_template
import os

# Get absolute paths
current_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(current_dir, "templates")

app = Flask(__name__, template_folder=template_dir)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    print(f"Template directory: {template_dir}")
    print(f"Template files: {os.listdir(template_dir)}")
    app.run(host='0.0.0.0', port=5002, debug=True)