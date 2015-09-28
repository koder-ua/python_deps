pip install -r requirements.txt

mkdir SOME_FIR
python deps.py collect SOME_DIR
python deps.py report SOME_DIR | tee report_file.txt
