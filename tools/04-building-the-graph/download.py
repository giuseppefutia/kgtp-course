import argparse
from datetime import datetime, timezone
import os
import json

import pandas as pd
import requests


class ChicagoDataDownloader:
    BASE_URL = "https://data.cityofchicago.org/api/views"

    def __init__(self, dataset_id=None):
        self.dataset_id = dataset_id

    def get_download_url(self):
        if not self.dataset_id:
            raise ValueError("Dataset ID is not set.")
        return f"{self.BASE_URL}/{self.dataset_id}/rows.csv?accessType=DOWNLOAD"

    def get_metadata_url(self):
        if not self.dataset_id:
            raise ValueError("Dataset ID is not set.")
        return f"{self.BASE_URL}/{self.dataset_id}.json"

    def download_data(self, save_path=None, outdir=None):
        url = self.get_download_url()
        response = requests.get(url, timeout=300)

        if response.status_code != 200:
            raise Exception(f"[✖] Failed to download data. HTTP Status: {response.status_code}")

        if not save_path:
            if outdir:
                os.makedirs(outdir, exist_ok=True)
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                save_path = os.path.join(outdir, f"{self.dataset_id}_{today}.csv")
            else:
                save_path = f"{self.dataset_id}.csv"

        parent = os.path.dirname(save_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(save_path, "wb") as f:
            f.write(response.content)

        print(f"[✔] Data downloaded and saved to '{save_path}'")
        return save_path

    def load_data(self, file_path=None):
        if not file_path:
            file_path = f"{self.dataset_id}.csv"

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"No such file: {file_path}")

        df = pd.read_csv(file_path)
        print(f"[✔] Loaded {len(df)} records from '{file_path}'")
        return df

    def get_metadata(self, outdir=None):
        url = self.get_metadata_url()
        response = requests.get(url, timeout=60)

        if response.status_code != 200:
            raise Exception(f"[✖] Failed to retrieve metadata. HTTP Status: {response.status_code}")

        meta = response.json()
        timestamp = meta.get("rowsUpdatedAt")
        updated_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)

        info = {
            "dataset_id": self.dataset_id,
            "name": meta.get("name"),
            "description": meta.get("description"),
            "rowsUpdatedAt": timestamp,
            "updatedAt": updated_at.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "columns": [col["name"] for col in meta.get("columns", [])],
        }

        # Always print (current behavior)
        print("=== Dataset Metadata ===")
        print(f"Dataset ID : {info['dataset_id']}")
        print(f"Name       : {info['name']}")
        print(f"Description: {info['description']}")
        print(f"Last Updated: {info['updatedAt']}")
        print(f"Columns    : {', '.join(info['columns'])}")

        # Optional: save to dated file
        if outdir:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            meta_dir = os.path.join(outdir, "metadata")
            os.makedirs(meta_dir, exist_ok=True)

            path = os.path.join(meta_dir, f"{self.dataset_id}_{today}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(info, f, indent=2)

            print(f"[✔] Metadata saved to '{path}'")

        return info


def main():
    parser = argparse.ArgumentParser(
        description="Download and inspect datasets from the City of Chicago Data Portal."
    )
    parser.add_argument("dataset_id", help="Socrata dataset ID (e.g., rsxa-ify5)")
    parser.add_argument("--metadata", action="store_true", help="Show dataset metadata")
    parser.add_argument("--download", action="store_true", help="Download dataset as CSV")
    parser.add_argument("--load", action="store_true", help="Load CSV into memory")
    parser.add_argument("--file", default=None, help="Path to save/load CSV")
    parser.add_argument("--outdir", default=None, help="Base folder for dated outputs")

    args = parser.parse_args()
    downloader = ChicagoDataDownloader(args.dataset_id)

    if args.metadata:
        downloader.get_metadata(outdir=args.outdir)

    if args.download:
        downloader.download_data(save_path=args.file, outdir=args.outdir)

    if args.load:
        downloader.load_data(file_path=args.file)


if __name__ == "__main__":
    main()
