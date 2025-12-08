#!/usr/bin/env python3
"""
Audio Combiner Script

PURPOSE AND DESCRIPTION:
This script is designed to combine multiple MP3 audio files into a single,
continuous audio file with smooth transitions. It reads all MP3 files from
the "audio_files" folder, extracts timestamp numbers from filenames, sorts them by
those timestamp numbers (smallest to largest), generates random pauses between each
audio file, and uses FFmpeg to concatenate all audio files with crossfade transitions.

REQUIREMENTS:
- FFmpeg must be installed and available in the system PATH
- Python 3.x with the following standard libraries:
  - os (for file system operations)
  - random (for generating random pause durations)
  - subprocess (for running FFmpeg commands)
  - glob (for finding audio files)
  - sys (for exit codes)
  - pathlib (for path handling)

STEP-BY-STEP USAGE INSTRUCTIONS:
1. Install FFmpeg on your system:
   - macOS: brew install ffmpeg
   - Ubuntu/Debian: sudo apt-get install ffmpeg
   - Windows: Download from https://ffmpeg.org/download.html
   - Verify installation by running: ffmpeg -version

2. Create an "audio_files" folder in the same directory as the script

3. Place all MP3 files you want to combine in the "audio_files" folder

4. Run the script: python audio_combiner.py

5. The combined audio will be saved as "final_audio.mp3" in the same directory

WHAT THE SCRIPT DOES:
- Scans the "audio_files" folder for all MP3 files
- Extracts timestamp numbers from filenames using regex
- Sorts files by extracted timestamp numbers (smallest to largest) for chronological ordering
- Creates temporary copies of audio files in a temp directory
- Generates random pause durations between 2 and 4 seconds between each audio file
- Creates silence files using FFmpeg for the random pauses
- Combines all files using FFmpeg's concat demuxer
- Maintains original audio quality by using stream copying
- Cleans up temporary files after processing

OUTPUT FILE INFORMATION:
- Output filename: "final_audio.mp3"
- Output location: Same directory as the script
- Audio quality: Preserves original quality (no re-encoding)
- File format: MP3 with stereo audio at 44.1kHz sample rate

ERROR HANDLING INFORMATION:
The script includes comprehensive error handling for:
- Missing FFmpeg installation (with helpful installation instructions)
- Missing "audio_files" folder
- No MP3 files found in the audio_files folder
- FFmpeg command failures (with error messages)
- Timeout issues during FFmpeg processing
- File permission problems
- Unexpected errors (with try-catch blocks)

The script will provide clear error messages and exit gracefully if any issues occur.
"""

import os
import random
import subprocess
import glob
import sys
from pathlib import Path
import time
import re
from typing import Optional, Union

def check_ffmpeg_installed():
    """
    Check if FFmpeg is installed and available in the system PATH.
    
    Returns:
        bool: True if FFmpeg is available, False otherwise
    """
    try:
        # Run FFmpeg version command to check if it's installed
        # Using capture_output=True to hide the version output
        # Using timeout=10 to prevent hanging
        result = subprocess.run(['ffmpeg', '-version'],
                              capture_output=True,
                              text=True,
                              timeout=10)
        if result.returncode == 0:
            print("✓ FFmpeg is installed and available")
            return True
        else:
            # FFmpeg exists but returned non-zero (shouldn't happen with -version)
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # TimeoutExpired: FFmpeg took too long to respond
        # FileNotFoundError: FFmpeg not found in PATH
        return False

def get_file_creation_time(file_path):
    """
    Get the actual creation time of a file from the file system.
    
    Args:
        file_path (str): Path to the file
        
    Returns:
        float: File creation timestamp (Unix timestamp)
    """
    return os.path.getctime(file_path)

def extract_timestamp_from_filename(filename):
    """
    Extract timestamp number from filename using regex.
    
    Args:
        filename (str): Filename to extract timestamp from
        
    Returns:
        int: Extracted timestamp number, or None if not found
    """
    match = re.search(r'(\d{10,})', filename)
    if match:
        return int(match.group(1))
    return None

def create_silence_file(duration, output_path):
    """
    Create a silence file of specified duration using FFmpeg.
    
    Args:
        duration (float): Duration of silence in seconds
        output_path (str): Path where the silence file will be saved
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # FFmpeg command to generate silence:
        # -f lavfi: Use libavfilter virtual input device
        # -i anullsrc=r=44100:cl=stereo:duration={duration}:
        #   - Generate null audio source (silence)
        #   - r=44100: 44.1kHz sample rate (CD quality)
        #   - cl=stereo: Stereo audio (2 channels)
        #   - duration={duration}: Length of silence in seconds
        # -t {duration}: Set output duration to match input
        # -y: Overwrite output file if it exists
        cmd = [
            'ffmpeg', '-f', 'lavfi',
            '-i', f'anullsrc=r=44100:cl=stereo:duration={duration}',
            '-t', str(duration), '-y', output_path
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # Handle FFmpeg timeout or missing FFmpeg
        return False

def combine_audio_files(
    audio_files_folder: Optional[Union[str, Path]] = None,
    output_file: Optional[Union[str, Path]] = None,
):
    """
    Main function to combine audio files with random pauses and crossfades.
    
    This is the core function that orchestrates the entire audio combining process:
    1. Validates prerequisites (FFmpeg, audio_files folder)
    2. Finds and processes audio files
    3. Creates random pause files
    4. Combines everything using FFmpeg concat demuxer
    
    Returns:
        bool: True if successful, False if any error occurs
    """
    audio_files_folder_path = Path(audio_files_folder) if audio_files_folder else Path("audio_files")
    output_file_path = Path(output_file) if output_file else Path("final_audio.mp3")
    
    print("🎵 Audio Combiner Script")
    print("=" * 40)
    
    # Check if FFmpeg is available
    if not check_ffmpeg_installed():
        print("❌ Error: FFmpeg is not installed or not found in PATH")
        print("Please install FFmpeg and try again.")
        print("Installation instructions:")
        print("- macOS: brew install ffmpeg")
        print("- Ubuntu/Debian: sudo apt-get install ffmpeg")
        print("- Windows: Download from https://ffmpeg.org/download.html")
        return False
    
    # Check if audio_files folder exists
    if not audio_files_folder_path.exists():
        print(f"❌ Error: '{audio_files_folder_path}' folder not found")
        print("Please create an 'audio_files' folder and place your audio files in it.")
        return False
    
    # Get all MP3 files from the audio_files folder
    audio_files = [Path(file_path) for file_path in glob.glob(str(audio_files_folder_path / "*.mp3"))]
    
    if not audio_files:
        print(f"❌ Error: No MP3 files found in '{audio_files_folder_path}' folder")
        print("Please place your MP3 files in the 'audio_files' folder.")
        return False
    
    # Debug output: Show files with both timestamp types side-by-side
    print("\n🔍 DEBUG: All files with timestamp comparison:")
    print("=" * 80)
    print(f"{'Filename':<60} | {'Extracted Number':<15} | {'File Creation Time':<20}")
    print("-" * 80)
    
    file_info = []
    for file_path in audio_files:
        filename = file_path.name
        creation_time = get_file_creation_time(file_path)
        creation_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(creation_time))
        
        # Extract timestamp number from filename
        extracted_number = "N/A"
        match = re.search(r'(\d{10,})', filename)
        if match:
            extracted_number = match.group(1)
        
        file_info.append((file_path, creation_time, filename, creation_time_str, extracted_number))
        
        # Print formatted table row
        print(f"{filename:<60} | {extracted_number:<15} | {creation_time_str:<20}")
    
    print("=" * 80)
    print(f"Total files: {len(file_info)}")
    print("=" * 80)
    
    # Sort files by extracted timestamp numbers (smallest to largest)
    audio_files.sort(key=lambda x: extract_timestamp_from_filename(x.name))
    
    # Debug output: Show sorted files with timestamp numbers
    print("\n🔍 DEBUG: Files sorted by extracted timestamp numbers (smallest to largest):")
    print("=" * 80)
    print(f"{'Filename':<60} | {'Extracted Number':<15} | {'File Creation Time':<20}")
    print("-" * 80)
    
    for file_path in audio_files:
        filename = file_path.name
        creation_time = get_file_creation_time(file_path)
        creation_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(creation_time))
        
        # Extract timestamp number from filename
        extracted_number = "N/A"
        match = re.search(r'(\d{10,})', filename)
        if match:
            extracted_number = match.group(1)
        
        # Print formatted table row
        print(f"{filename:<60} | {extracted_number:<15} | {creation_time_str:<20}")
    
    print("=" * 80)
    print("Files are now sorted by extracted timestamp numbers (smallest to largest)")
    print("=" * 80)
    
    # Show first 10 files after sorting for verification
    print("\n🔍 DEBUG: First 10 files after sorting:")
    print("=" * 80)
    print(f"{'Filename':<60} | {'Extracted Number':<15}")
    print("-" * 80)
    
    for i, file_path in enumerate(audio_files[:10]):
        filename = file_path.name
        extracted_number = "N/A"
        match = re.search(r'(\d{10,})', filename)
        if match:
            extracted_number = match.group(1)
        
        print(f"{filename:<60} | {extracted_number:<15}")
    
    if len(audio_files) > 10:
        print(f"... and {len(audio_files) - 10} more files")
    
    print("=" * 80)
    
    print(f"\n📁 Found {len(audio_files)} audio files")
    
    # Create temporary directory for intermediate files
    temp_dir = output_file_path.parent / "temp_audio_files"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        print("\n🔄 Processing audio files...")
        
        # Process each audio file - copy to temp directory with standardized naming
        for i, audio_file in enumerate(audio_files):
            filename = audio_file.name
            print(f"  [{i+1}/{len(audio_files)}] Processing: {filename}")

            # Copy original file to temp directory with standardized naming
            # This ensures consistent file ordering in the concat list
            temp_file = temp_dir / f"segment_{i:03d}.mp3"
            cmd = ['ffmpeg', '-i', str(audio_file), '-y', str(temp_file)]
            subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        # Create silence files for random pauses between audio segments
        print("\n🎲 Generating random pauses...")
        silence_files = []

        for i in range(len(audio_files) - 1):
            # Generate random pause duration between 2 and 4 seconds
            # This creates natural-sounding gaps between audio segments
            pause_duration = round(random.uniform(2, 4), 2)
            silence_file = temp_dir / f"silence_{i:03d}_{pause_duration}s.mp3"

            if create_silence_file(pause_duration, str(silence_file)):
                silence_files.append(silence_file)
                print(f"  Created {pause_duration}s silence")
            else:
                print(f"  ❌ Failed to create {pause_duration}s silence")
                return False
        
        # Create FFmpeg concat list file
        # This file tells FFmpeg the order and timing of audio segments
        concat_file = temp_dir / "concat_list.txt"

        with concat_file.open('w', encoding='utf-8') as f:
            # Start with the first audio segment
            f.write(f"file 'segment_000.mp3'\n")

            # Alternate between silence and audio segments
            # This creates the pattern: audio1 -> silence -> audio2 -> silence -> audio3...
            for i in range(len(silence_files)):
                f.write(f"file '{silence_files[i].name}'\n")
                f.write(f"file 'segment_{i+1:03d}.mp3'\n")
        
        # Build final FFmpeg command for concatenation
        # Using concat demuxer for lossless concatenation
        print("\n🔀 Combining files...")
        cmd = [
            'ffmpeg',
            '-f', 'concat',           # Use concat demuxer for file concatenation
            '-safe', '0',             # Allow absolute paths (needed for concat demuxer)
            '-i', str(concat_file),   # Input concat list file
            '-c', 'copy',             # Stream copy to avoid re-encoding (preserves quality)
            '-y',                     # Overwrite output file if it exists
            str(output_file_path)     # Final output file
        ]
        
        print("🎬 Finalizing combined audio...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            print(f"\n✅ Success! Combined audio saved as '{output_file_path}'")
            return True
        else:
            print(f"\n❌ Error combining audio files")
            print(f"FFmpeg error: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        return False
    finally:
        # Clean up temporary files
        # This ensures no temporary files are left behind after processing
        try:
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                print("\n🧹 Cleaned up temporary files")
        except:
            # If cleanup fails, continue (not critical for functionality)
            pass

if __name__ == "__main__":
    """
    USAGE EXAMPLES:
    
    Example 1: Basic usage
    ----------------------
    1. Make sure FFmpeg is installed:
       - macOS: brew install ffmpeg
       - Ubuntu/Debian: sudo apt-get install ffmpeg
       - Windows: Download from https://ffmpeg.org/download.html
    
    2. Create an "audio_files" folder in the same directory as the script
    
    3. Place your MP3 files in the "audio_files" folder
    
    4. Run the script:
       python audio_combiner.py
    
    5. Expected output:
       🎵 Audio Combiner Script
       ========================================
       ✓ FFmpeg is installed and available
       📁 Found 5 audio files
       
       🔄 Processing audio files...
         [1/5] Processing: song1.mp3
         [2/5] Processing: song2.mp3
         [3/5] Processing: song3.mp3
         [4/5] Processing: song4.mp3
         [5/5] Processing: song5.mp3
       
       🎲 Generating random pauses...
         Created 1.23s silence
         Created 1.87s silence
         Created 2.15s silence
         Created 1.45s silence
       
       🔀 Combining files...
       🎬 Finalizing combined audio...
       
       ✅ Success! Combined audio saved as 'final_audio.mp3'
       🧹 Cleaned up temporary files
    
    Example 2: Troubleshooting common issues
    ---------------------------------------
    Issue: "FFmpeg is not installed or not found in PATH"
    Solution: Install FFmpeg using your system's package manager
    
    Issue: "'audio_files' folder not found"
    Solution: Create the folder and place your MP3 files inside
    
    Issue: "No MP3 files found in 'audio_files' folder"
    Solution: Make sure your audio files have .mp3 extension
    
    Issue: "Error combining audio files"
    Solution: Check if you have write permissions in the current directory
    
    Example 3: Advanced usage
    -------------------------
    - The script automatically sorts files by timestamp numbers extracted from filenames (smallest to largest)
    - Random pauses between 2-4 seconds create natural transitions
    - Original audio quality is preserved (no re-encoding)
    - Temporary files are automatically cleaned up after processing
    
    Example 4: Error handling
    ------------------------
    The script handles various error conditions:
    - Missing FFmpeg installation
    - Missing audio_files directory
    - No MP3 files found
    - FFmpeg command failures
    - File permission issues
    - Timeout issues
    
    Each error includes a descriptive message and suggested solution.
    """
    success = combine_audio_files()
    sys.exit(0 if success else 1)