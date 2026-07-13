import os
import json
from http.server import SimpleHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get('PORT', 3000))
LIVE_DATA_DIR = os.path.join(os.getcwd(), 'live_data')

# Ensure live_data directory exists
if not os.path.exists(LIVE_DATA_DIR):
    os.makedirs(LIVE_DATA_DIR)

class LocalTelemetryHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Allow CORS (in case of browser calls)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        # Path structure: /api/telemetry/:unitId
        path_parts = self.path.strip('/').split('/')
        if len(path_parts) >= 2 and path_parts[0] == 'api' and path_parts[1] == 'telemetry':
            unit_id = path_parts[-1]
            filename = f"latest_{unit_id}.json"
            filepath = os.path.join(LIVE_DATA_DIR, filename)
            
            if os.path.exists(filepath):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                with open(filepath, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"No telemetry data found for unit {unit_id}"}).encode('utf-8'))
            return
        
        # Fallback to serving static files from frontend/dist
        super().do_GET()

    def translate_path(self, path):
        # Serve static files from the docs folder at the root
        clean_path = path.split('?')[0].split('#')[0]
        dist_dir = os.path.join(os.getcwd(), 'docs')
        target_path = os.path.join(dist_dir, clean_path.lstrip('/'))
        
        # For base route or missing files (SPA routing), fallback to index.html
        if clean_path == '/' or not os.path.exists(target_path) or os.path.isdir(target_path):
            return os.path.join(dist_dir, 'index.html')
            
        return target_path

    def do_PUT(self):
        self.handle_write()

    def do_POST(self):
        self.handle_write()

    def handle_write(self):
        # Path structure: /api/telemetry/:unitId
        path_parts = self.path.strip('/').split('/')
        if len(path_parts) >= 2 and path_parts[0] == 'api' and path_parts[1] == 'telemetry':
            unit_id = path_parts[-1]
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body.decode('utf-8'))
                
                # Format to match Streamlit fallback files
                filename = f"latest_{unit_id}.json"
                filepath = os.path.join(LIVE_DATA_DIR, filename)
                
                with open(filepath, 'w') as f:
                    json.dump(payload, f)
                
                print(f"[Telemetry Received] Saved telemetry for Unit {unit_id} to local files.")
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            except Exception as e:
                print(f"[Error] Failed to process telemetry: {e}")
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return
        
        self.send_response(404)
        self.end_headers()

if __name__ == '__main__':
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, LocalTelemetryHandler)
    print(f"==================================================")
    print(f"📡 REMAC Local Telemetry Receiver is running!")
    print(f"==================================================")
    print(f"1. Connect your NodeMCU and PC to the same Wi-Fi Hotspot.")
    print(f"2. Your server port is: {PORT}")
    print(f"3. Leave this script running in the background.")
    print(f"==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local receiver...")
        httpd.server_close()
