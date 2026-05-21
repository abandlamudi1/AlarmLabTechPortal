"""Description parser for Jira Lab Request tickets.

Extracts system details from Jira wiki markup formatted descriptions.
"""
import re
from typing import Any, Dict, List, Optional, Tuple


class DescriptionParser:
    """Parse structured data from Jira Lab Request ticket descriptions."""
    
    @staticmethod
    def _parse_jira_table(description: str) -> List[Dict[str, str]]:
        """Parse Jira wiki markup tables into list of row dictionaries.
        
        Jira format allows newlines and blank lines within cells:
        ||Header1||Header2||Header3||
        |Value1 with
        
        blank lines|Value2|Value3|
        
        The challenge: cells can contain multiple newlines and even blank lines.
        We identify row boundaries by looking for:
        - Row start: line starting with exactly one |
        - Row end: line ending with exactly one |
        
        Returns:
            List of dicts mapping header -> value for each data row
        """
        rows = []
        lines = description.split('\n')
        
        current_headers = []
        row_buffer = []
        in_data_row = False
        
        i = 0
        while i < len(lines):
            line = lines[i]
            line_stripped = line.strip()
            
            # Header row: ||Header1||Header2||Header3||
            if line_stripped.startswith('||') and line_stripped.endswith('||'):
                # Save any pending row first
                if in_data_row and row_buffer and current_headers:
                    rows.append(DescriptionParser._finalize_table_row(row_buffer, current_headers))
                    row_buffer = []
                    in_data_row = False
                
                # Parse headers
                headers = [h.strip() for h in line_stripped.split('||') if h.strip()]
                current_headers = headers
                i += 1
                continue
            
            # Data row start: |Value... (but NOT ||)
            if line_stripped.startswith('|') and not line_stripped.startswith('||'):
                # Save any pending row first
                if in_data_row and row_buffer and current_headers:
                    rows.append(DescriptionParser._finalize_table_row(row_buffer, current_headers))
                    row_buffer = []
                
                # Start accumulating this data row
                in_data_row = True
                row_buffer.append(line_stripped)
                
                # Check if row ends on same line (ends with |)
                if line_stripped.endswith('|'):
                    # Complete row on one line
                    rows.append(DescriptionParser._finalize_table_row(row_buffer, current_headers))
                    row_buffer = []
                    in_data_row = False
                
                i += 1
                continue
            
            # If we're in a data row, keep accumulating until we find row end
            if in_data_row:
                # Check for terminators that end the table
                if line_stripped.startswith('{panel') or line_stripped.startswith('----'):
                    # Table ended, save row
                    if row_buffer and current_headers:
                        rows.append(DescriptionParser._finalize_table_row(row_buffer, current_headers))
                    row_buffer = []
                    in_data_row = False
                    current_headers = []
                    i += 1
                    continue
                
                # Section headers also end tables
                if line_stripped.startswith('*') and line_stripped.endswith('*'):
                    if row_buffer and current_headers:
                        rows.append(DescriptionParser._finalize_table_row(row_buffer, current_headers))
                    row_buffer = []
                    in_data_row = False
                    i += 1
                    continue
                
                # Add line to row buffer (even if blank - might be within a cell)
                row_buffer.append(line_stripped)
                
                # Check if this line ends with | (row complete)
                if line_stripped.endswith('|'):
                    rows.append(DescriptionParser._finalize_table_row(row_buffer, current_headers))
                    row_buffer = []
                    in_data_row = False
                
                i += 1
                continue
            
            i += 1
        
        # Save any final pending row
        if in_data_row and row_buffer and current_headers:
            rows.append(DescriptionParser._finalize_table_row(row_buffer, current_headers))
        
        return rows
    
    @staticmethod
    def _finalize_table_row(row_lines: List[str], headers: List[str]) -> Dict[str, str]:
        """Convert accumulated row lines into a dictionary mapping headers to values.
        
        Args:
            row_lines: Lines that make up the table row (might include blank lines within cells)
            headers: Column headers for this table
            
        Returns:
            Dict mapping header -> cell value
        """
        # Combine all lines back into one string
        row_text = '\n'.join(row_lines)
        
        # Remove leading and trailing |
        if row_text.startswith('|'):
            row_text = row_text[1:]
        if row_text.endswith('|'):
            row_text = row_text[:-1]
        
        # Split by | to get cell values
        values = row_text.split('|')
        
        # If we don't have the right number of columns, return empty dict
        if len(values) != len(headers):
            return {}
        
        # Clean up values (preserve internal newlines but strip leading/trailing whitespace)
        values_cleaned = [v.strip() for v in values]
        
        return dict(zip(headers, values_cleaned))
    
    @staticmethod
    def extract_location(summary: str, description: str) -> Dict[str, Optional[str]]:
        """Extract location_number and location_name from summary and description.
        
        Args:
            summary: Issue summary (e.g., "10-640- SmokeTest - Test - Username: Climax RPM")
            description: Full issue description
            
        Returns:
            Dict with keys: location_number, location_name
        """
        location = {
            "location_number": None,
            "location_name": None,
        }
        
        # Try to parse from summary: "10-640- ..." format
        # Extract as Location Number (e.g., "10-640")
        summary_match = re.match(r'^(\d+)-(\d+)', summary.strip())
        if summary_match:
            building = summary_match.group(1)  # "10"
            room = summary_match.group(2)  # "640"
            location["location_number"] = f"{building}-{room}"  # "10-640"
        
        # Extract location name from description
        # Look for "Floor" mentions (e.g., "# 10 Floor" -> "Floor 10")
        floor_match = re.search(r'#\s*(\d+)\s+Floor', description, re.IGNORECASE)
        if floor_match:
            floor_name = f"Floor {floor_match.group(1)}"
            location["location_name"] = floor_name
        
        # Look for explicit location markers in description tables
        table_rows = DescriptionParser._parse_jira_table(description)
        for row in table_rows:
            # Check for "Suites running on system" which contains floor/location info
            if "Suites running on system" in row:
                suite_value = row["Suites running on system"].strip()
                if suite_value and suite_value != "na":
                    # e.g., "# 10 Floor" -> "Floor 10"
                    floor_match = re.search(r'#?\s*(\d+)\s+Floor', suite_value, re.IGNORECASE)
                    if floor_match and not location["location_name"]:
                        location["location_name"] = f"Floor {floor_match.group(1)}"
        
        return location
    
    @staticmethod
    def extract_identifiers(description: str, summary: str = "") -> List[Dict[str, str]]:
        """Extract system identifiers (CID, Username, IMEI, MAC, etc.) from description.
        
        Args:
            description: Full issue description
            summary: Issue summary (may contain username)
            
        Returns:
            List of dicts with keys: label, value, source
        """
        identifiers = []
        seen_values = set()  # Avoid duplicates
        
        # Parse Jira tables
        table_rows = DescriptionParser._parse_jira_table(description)
        
        # Field name mappings (case-insensitive)
        field_mappings = {
            "cid": "CID",
            "username": "Username",
            "password": "Password",  
            "imei": "IMEI",
            "alarm.com serial # (imei)": "IMEI",
            "system email": "Email",
            "raspi mac": "MAC Address",
            "mac": "MAC Address",
        }
        
        # Extract from tables
        for row in table_rows:
            for header, value in row.items():
                header_lower = header.lower().strip()
                value_clean = value.strip()
                
                # Skip empty or placeholder values
                if not value_clean or value_clean.lower() in ['na', 'n/a', 'none', '']:
                    continue
                
                # Check if this is a known field
                label = None
                for field_key, field_label in field_mappings.items():
                    if field_key in header_lower:
                        label = field_label
                        break
                
                # If we found a matching field and haven't seen this value
                if label and value_clean not in seen_values:
                    identifiers.append({
                        "label": label,
                        "value": value_clean,
                        "source": "table"
                    })
                    seen_values.add(value_clean)
        
        # Extract username from summary if not already found (e.g., "Username: Climax RPM")
        if summary and not any(i['label'] == 'Username' for i in identifiers):
            username_in_summary = re.search(r'Username:\s*([^\s-]+(?:\s+[^\s-]+)*)', summary)
            if username_in_summary:
                username = username_in_summary.group(1).strip()
                if username and username.lower() not in ["na", "n/a"] and username not in seen_values:
                    identifiers.append({
                        "label": "Username",
                        "value": username,
                        "source": "summary"
                    })
                    seen_values.add(username)
        
        # Also check for CID in summary as fallback
        if not any(i['label'] == 'CID' for i in identifiers):
            cid_match = re.search(r'\b([0-9]{8})\b', description)
            if cid_match:
                cid = cid_match.group(1)
                if cid not in seen_values:
                    identifiers.append({
                        "label": "CID",
                        "value": cid,
                        "source": "description"
                    })
                    seen_values.add(cid)
        
        return identifiers
    
    @staticmethod
    def extract_system_name(summary: str, description: str) -> str:
        """Extract system name from summary or description.
        
        Args:
            summary: Issue summary
            description: Full issue description
            
        Returns:
            System name string
        """
        # Try to parse from summary: "10-640- SmokeTest - Test - Username: Climax RPM"
        # Remove location number prefix and extract meaningful part
        name = summary
        
        # Remove location number prefix (e.g., "10-640-")
        name = re.sub(r'^\d+-\d+-?\s*', '', name).strip()
        
        # Remove "Username: xxx" suffix if present
        name = re.sub(r'\s*-?\s*Username:\s*[^\s-]+.*$', '', name).strip()
        
        # If name is too short, use summary as-is
        if len(name) < 3:
            name = summary
        
        return name
    
    @staticmethod
    def extract_panel_type(description: str) -> Optional[str]:
        """Extract panel type from description.
        
        Args:
            description: Full issue description
            
        Returns:
            Panel type (e.g., "Climax") or None
        """
        # Parse tables and look for Panel column
        table_rows = DescriptionParser._parse_jira_table(description)
        
        for row in table_rows:
            for header, value in row.items():
                if 'panel' in header.lower():
                    panel = value.strip()
                    if panel and panel.lower() not in ['na', 'n/a', 'none', '']:
                        return panel
        
        # Look for common panel keywords in description
        for panel_type in ['Climax', 'Qolsys', '2GIG', 'Honeywell', 'DSC', 'GE', 'Interlogix']:
            if re.search(rf'\b{panel_type}\b', description, re.IGNORECASE):
                return panel_type
        
        return None
    
    @staticmethod
    def extract_devices(description: str) -> List[str]:
        """Extract device list from description.
        
        Args:
            description: Full issue description
            
        Returns:
            List of device descriptions
        """
        devices = []
        
        # Parse tables
        table_rows = DescriptionParser._parse_jira_table(description)
        
        for row in table_rows:
            for header, value in row.items():
                header_lower = header.lower().strip()
                value_clean = value.strip()
                
                # Skip empty values
                if not value_clean or value_clean.lower() in ['na', 'n/a', 'none', '']:
                    continue
                
                # Extract different device types
                if 'sensor' in header_lower:
                    # Parse sensor descriptions (e.g., "1 Front Door\n2 Back")
                    sensor_items = re.findall(r'(\d+\s+[^\n]+)', value_clean)
                    for item in sensor_items:
                        devices.append(f"Sensor: {item.strip()}")
                    if not sensor_items and value_clean:
                        devices.append(f"Sensors: {value_clean}")
                        
                elif 'zwave' in header_lower or 'zigbee' in header_lower:
                    # Parse zWave/Zigbee devices (e.g., "ID: 2 Thermostat\nID: 7 Thermostat")
                    device_items = re.findall(r'ID:\s*(\d+\s+[^\n]+)', value_clean)
                    for item in device_items:
                        devices.append(f"zWave/Zigbee: {item.strip()}")
                        
                elif 'camera' in header_lower:
                    devices.append(f"Camera: {value_clean}")
                    
                elif 'lock' in header_lower:
                    devices.append(f"Lock: {value_clean}")
                    
                elif 'thermostat' in header_lower:
                    devices.append(f"Thermostat: {value_clean}")
        
        return devices
    
    @staticmethod
    def extract_notes(description: str) -> str:
        """Extract notes or special instructions from description.
        
        Args:
            description: Full issue description
            
        Returns:
            Notes/instructions text
        """
        notes_parts = []
        
        # Extract setup instructions
        instructions_match = re.search(
            r'\{panel:title=Setup\s+instructions.*?\}(.*?)\{panel\}',
            description,
            re.IGNORECASE | re.DOTALL
        )
        if instructions_match:
            instructions = instructions_match.group(1).strip()
            # Clean up wiki markup
            instructions = re.sub(r'\{panel.*?\}', '', instructions)
            instructions = instructions.strip()
            if instructions and len(instructions) > 10:
                notes_parts.append(f"Setup Instructions: {instructions}")
        
        # If no specific notes found, use first 200 chars of description as notes
        if not notes_parts:
            clean_desc = re.sub(r'\{panel.*?\}', '', description)
            clean_desc = re.sub(r'\|\|.*?\|\|', '', clean_desc)
            clean_desc = re.sub(r'\|', ' ', clean_desc)
            clean_desc = ' '.join(clean_desc.split())  # Normalize whitespace
            if len(clean_desc) > 200:
                notes_parts.append(clean_desc[:200] + "...")
            elif clean_desc:
                notes_parts.append(clean_desc)
        
        return '\n\n'.join(notes_parts) if notes_parts else "Imported from Jira"


def parse_ticket_for_system(issue: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a Jira issue and extract system locator fields.
    
    Args:
        issue: Jira issue dict with 'key', 'fields', etc.
        
    Returns:
        Dict suitable for system locator with extracted fields
    """
    fields = issue.get("fields", {})
    summary = fields.get("summary", "")
    description = fields.get("description", "")
    
    location = DescriptionParser.extract_location(summary, description)
    identifiers = DescriptionParser.extract_identifiers(description, summary)
    system_name = DescriptionParser.extract_system_name(summary, description)
    panel_type = DescriptionParser.extract_panel_type(description)
    devices = DescriptionParser.extract_devices(description)
    notes = DescriptionParser.extract_notes(description)
    
    # Add panel type to notes if found
    if panel_type:
        notes = f"Panel: {panel_type}\n\n" + notes
    
    # Add devices to notes if found
    if devices:
        devices_text = "\n".join([f"- {dev}" for dev in devices])
        notes = notes + f"\n\nDevices:\n{devices_text}"
    
    return {
        "name": system_name,
        "location_number": location["location_number"],
        "location_name": location["location_name"],
        "status": "Active",  # Default status
        "notes": notes,
        "jira_issue_key": issue.get("key"),
        "identifiers": identifiers,
    }
