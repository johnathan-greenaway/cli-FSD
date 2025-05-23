import os

def list_files(directory):
    try:
        files = os.listdir(directory)
        print(f"Files in {directory}:")
        for file in files:
            print(file)
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == '__main__':
    list_files('/home/icarus/Local-Projects-WSL/2025/cli-FSD-2025/cli-FSD/test-tok')