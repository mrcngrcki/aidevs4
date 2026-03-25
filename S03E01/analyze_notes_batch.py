import os
import json
from openai import OpenAI
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv, find_dotenv

class NoteClassification(BaseModel):
    note_id: int
    is_ok: bool

class BatchNotesResponse(BaseModel):
    results: List[NoteClassification]

def process_notes():
    load_dotenv(find_dotenv())
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    base_dir = "xxx"
    notes_file = os.path.join(base_dir, "notes.json")
    valid_files_path = os.path.join(base_dir, "valid_files.json")
    invalid_files_path = os.path.join(base_dir, "invalid_files.json")

    with open(notes_file, 'r') as f:
        notes_mapping = json.load(f)
    
    unique_notes = list(notes_mapping.keys())
    print(f"Total unique notes to process: {len(unique_notes)}")

    # Load current valid/invalid lists
    with open(valid_files_path, 'r') as f:
        valid_files = json.load(f)
    with open(invalid_files_path, 'r') as f:
        invalid_files = json.load(f)

    chunk_size = 400
    false_notes = []

    for i in range(0, len(unique_notes), chunk_size):
        chunk = unique_notes[i : i + chunk_size]
        print(f"Processing chunk {i//chunk_size + 1}/{(len(unique_notes)-1)//chunk_size + 1}...")
        
        notes_text = "\n".join([f"ID: {idx} | Note: {note}" for idx, note in enumerate(chunk)])
        
        prompt = f"""Analyze the following operator notes (marked with ID). 
Determine if each note indicates that everything is working correctly (is_ok: true) 
or if there is an error, warning, suspicious behavior, or something 'concerning' (is_ok: false).
Return a structured JSON with a list of results containing 'note_id' and 'is_ok'.

Notes:
{notes_text}"""

        completion = client.beta.chat.completions.parse(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": "You are a specialized sensor data analyst."},
                {"role": "user", "content": prompt}
            ],
            response_format=BatchNotesResponse
        )
        
        parsed_results = completion.choices[0].message.parsed.results
        for res in parsed_results:
            if not res.is_ok:
                false_notes.append(chunk[res.note_id])

    print(f"Found {len(false_notes)} notes indicating issues.")

    # Update valid/invalid lists
    valid_files_set = set(valid_files)
    invalid_files_set = set(invalid_files)
    
    files_to_move = []
    for note in false_notes:
        files_to_move.extend(notes_mapping[note])
    
    moved_count = 0
    for filename in files_to_move:
        if filename in valid_files_set:
            valid_files_set.remove(filename)
            invalid_files_set.add(filename)
            moved_count += 1
    
    # Save updated lists
    with open(valid_files_path, 'w') as f:
        json.dump(sorted(list(valid_files_set)), f, indent=2)
    with open(invalid_files_path, 'w') as f:
        json.dump(sorted(list(invalid_files_set)), f, indent=2)

    print(f"Moved {moved_count} files to invalid_files.json.")
    print(f"Final counts: Valid: {len(valid_files_set)}, Invalid: {len(invalid_files_set)}")

if __name__ == "__main__":
    process_notes()
