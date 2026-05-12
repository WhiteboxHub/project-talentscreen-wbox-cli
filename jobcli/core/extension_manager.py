"""Manager for automatically downloading and extracting Chrome extensions."""

import os
import tempfile
import zipfile
import urllib.request
from pathlib import Path

from rich.console import Console

console = Console()

class ExtensionManager:
    """Handles programmatic downloading and extraction of Chrome extensions from the Web Store."""
    
    # Official Chrome Web Store API endpoint for downloading CRX files
    CRX_DOWNLOAD_URL = "https://clients2.google.com/service/update2/crx?response=redirect&prodversion=99.0&acceptformat=crx2,crx3&x=id%3D{extension_id}%26uc"
    
    @staticmethod
    def download_and_extract(extension_id: str, dest_dir: Path) -> bool:
        """Download an extension by ID and extract it to the destination directory.
        
        Args:
            extension_id: The 32-character Chrome extension ID
            dest_dir: The directory where the extension should be unpacked
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            url = ExtensionManager.CRX_DOWNLOAD_URL.format(extension_id=extension_id)
            dest_dir.mkdir(parents=True, exist_ok=True)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".crx") as temp_file:
                temp_crx_path = temp_file.name
                
            console.print(f"  [dim]Downloading extension {extension_id}...[/dim]")
            
            # Setting a User-Agent is sometimes required by Google endpoints
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36'}
            )
            
            with urllib.request.urlopen(req) as response, open(temp_crx_path, 'wb') as out_file:
                out_file.write(response.read())
                
            console.print("  [dim]Extracting extension...[/dim]")
            
            # Extract the CRX (which is a zip archive with a custom header)
            try:
                with zipfile.ZipFile(temp_crx_path, 'r') as zip_ref:
                    zip_ref.extractall(dest_dir)
            except zipfile.BadZipFile:
                # The first few bytes of a CRX contain a header before the ZIP payload starts
                with open(temp_crx_path, 'rb') as f:
                    data = f.read()
                    
                # Find the start of the zip archive (PK\x03\x04)
                zip_start = data.find(b'PK\x03\x04')
                if zip_start == -1:
                    console.print(f"  [red]✗ Could not find ZIP payload in the downloaded CRX file.[/red]")
                    return False
                    
                with open(temp_crx_path, 'wb') as f:
                    f.write(data[zip_start:])
                    
                with zipfile.ZipFile(temp_crx_path, 'r') as zip_ref:
                    zip_ref.extractall(dest_dir)
                    
            # Cleanup temp file
            try:
                os.remove(temp_crx_path)
            except OSError:
                pass
            
            # Verify manifest.json exists
            if not (dest_dir / "manifest.json").exists():
                console.print(f"  [red]✗ Extracted successfully but no manifest.json found.[/red]")
                return False
                
            return True
            
        except Exception as e:
            console.print(f"  [red]✗ Failed to download/extract extension: {e}[/red]")
            return False
