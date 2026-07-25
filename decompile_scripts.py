import os
import zlib
import pickle
import subprocess
import glob

rpa_path = "/home/bgkang/Projects/DDCC/DDLC-1.1.1-pc/game/scripts.rpa"
output_dir = "/home/bgkang/Projects/DDCC/game_scripts"

os.makedirs(output_dir, exist_ok=True)

print(f"Reading archive: {rpa_path}")
with open(rpa_path, "rb") as f:
    header = f.readline().decode("utf-8")
    parts = header.split()
    if len(parts) < 3 or parts[0] != "RPA-3.0":
        print("Error: Unsupported RPA version or invalid header.")
        exit(1)
        
    offset = int(parts[1], 16)
    key = int(parts[2], 16)
    
    f.seek(offset)
    index_data = f.read()
    decompressed = zlib.decompress(index_data)
    index = pickle.loads(decompressed)
    
    print(f"Found {len(index)} files in archive. Extracting...")
    
    for filename, entry in index.items():
        # Deobfuscate offset and length and read file contents
        file_bytes = b""
        for offset_obf, length_obf, *extra in entry:
            actual_offset = offset_obf ^ key
            actual_length = length_obf ^ key
            f.seek(actual_offset)
            file_bytes += f.read(actual_length)
            
        out_filepath = os.path.join(output_dir, filename)
        with open(out_filepath, "wb") as out_f:
            out_f.write(file_bytes)
        print(f" - Extracted: {filename} ({len(file_bytes)} bytes)")

print("\nDecompiling .rpyc files using rpycdec...")
rpyc_files = glob.glob(os.path.join(output_dir, "*.rpyc"))

for rpyc_file in rpyc_files:
    print(f"Decompiling {os.path.basename(rpyc_file)}...")
    subprocess.run(["rpycdec", "decompile", rpyc_file], check=True)
    # Remove the .rpyc file after successful decompilation
    os.remove(rpyc_file)

print("\nAll scripts extracted and decompiled successfully to:", output_dir)
