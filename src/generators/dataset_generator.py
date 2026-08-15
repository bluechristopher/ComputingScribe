"""
EduScribe AI - Dataset Generator Module
Generates balanced synthetic companion datasets (CSV, SQL, Python starter files)
with strict demographic fairness (50/50 gender balance and Singapore/regional multiracial naming pools).
"""

import json
import random
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from config.gcp_config import AppConfig

# Authentic multiracial naming pools
ETHNIC_NAMES = {
    "Chinese": {
        "Male": ["Wei Ming", "Jun Jie", "Zheng Yang", "Jian Hao", "Kai Wen", "Zhi Wei", "Marcus Tan", "Darren Lim"],
        "Female": ["Mei Ling", "Xin Yi", "Pei Shan", "Hui Min", "Rachel Wong", "Chloe Ng", "Si Ying", "Jolene Koh"]
    },
    "Malay": {
        "Male": ["Muhammad Danial", "Ahmad Farhan", "Nur Irfan", "Harith Iskandar", "Hafiz Bin Rahim", "Zulqarnain"],
        "Female": ["Nurul Aisyah", "Siti Sarah", "Farah Nadiah", "Nadhirah Binte Hassan", "Aleeya Maisarah", "Yasmin"]
    },
    "Indian": {
        "Male": ["Rahul Sharma", "Karthik Raja", "Pravin Kumar", "Sanjay Menon", "Arun S/O Vijayan", "Vikram Nair"],
        "Female": ["Priya Shankar", "Divya Lakshmi", "Ananya Sundaram", "Kavitha D/O Muthu", "Deepa Pillai", "Sneha"]
    },
    "Eurasian_Caucasian": {
        "Male": ["Alexander De Silva", "Lucas Fernandez", "Ethan Rodrigues", "Oliver Smith", "Daniel Clarke"],
        "Female": ["Emily Pereira", "Jessica Sta Maria", "Sophia D'Almeida", "Charlotte Brown", "Hannah Jones"]
    }
}

class DatasetRecord(BaseModel):
    id: int
    name: str
    gender: str
    ethnicity: str
    attributes: Dict[str, Any]

class SyntheticDataset(BaseModel):
    title: str
    description: str
    filename: str
    file_type: str = Field(description="'csv', 'sql', or 'txt'")
    columns: List[str]
    records: List[Dict[str, Any]]
    csv_content: str
    sql_schema_content: Optional[str] = None
    starter_python_code: Optional[str] = None

class DatasetGenerator:
    def __init__(self):
        pass

    def _sample_demographic_names(self, count: int = 10) -> List[Dict[str, str]]:
        """
        Generates demographically balanced names:
        50/50 gender balance across Chinese, Malay, Indian, Eurasian/Caucasian.
        """
        pool = []
        ethnicities = list(ETHNIC_NAMES.keys())
        # Target ~70% Chinese, 15% Malay, 10% Indian, 5% Eurasian/Caucasian for typical Singapore distribution,
        # or evenly balanced across multiracial groups.
        groups = ["Chinese", "Chinese", "Chinese", "Malay", "Malay", "Indian", "Indian", "Eurasian_Caucasian"]
        
        genders = ["Male", "Female"]
        for i in range(count):
            eth = random.choice(groups)
            gender = genders[i % 2] # Strict 50/50 toggle
            name = random.choice(ETHNIC_NAMES[eth][gender])
            pool.append({
                "name": name,
                "gender": gender,
                "ethnicity": eth
            })
        random.shuffle(pool)
        return pool

    def generate_dataset(
        self,
        domain_topic: str,
        record_count: int = 12,
        preferred_format: str = "csv"
    ) -> SyntheticDataset:
        """
        Generates realistic tabular test datasets with deterministic demographic parity.
        Uses Gemini 3.7 Flash or structured rules engine.
        """
        names_sample = self._sample_demographic_names(record_count)
        
        prompt = f"""
You are an expert computing examination data synthesizer.
Generate a realistic examination test dataset for the topic: '{domain_topic}'.
Format requirement: {preferred_format.upper()}

The dataset MUST strictly integrate these {len(names_sample)} pre-allocated candidate demographic records:
{json.dumps(names_sample, indent=2)}

Create appropriate domain attributes (e.g. TestScores, AccountBalance, LibraryLoans, TransactionHistory, SensorReadings) based on '{domain_topic}'.

Return a valid JSON object matching this schema:
{{
  "title": "Short title of dataset",
  "description": "Examination context description",
  "filename": "e.g. STUDENTS.csv or INVENTORY.txt",
  "file_type": "csv",
  "columns": ["StudentID", "FullName", "Gender", "Score1", "Score2", "Grade"],
  "records": [
    {{"StudentID": "S101", "FullName": "Wei Ming", "Gender": "Male", "Score1": 85, "Score2": 92, "Grade": "A"}},
    ...
  ],
  "csv_content": "StudentID,FullName,Gender,Score1,Score2,Grade\\nS101,Wei Ming,Male,85,92,A\\n...",
  "sql_schema_content": "CREATE TABLE Students (...);\\nINSERT INTO Students VALUES (...);",
  "starter_python_code": "# Python skeleton code to read and process this dataset\\nimport csv\\n..."
}}
"""
        client = AppConfig.get_gemini_client()
        if client and hasattr(client, "GenerativeModel"):
            try:
                model = client.GenerativeModel(AppConfig.DEFAULT_MODEL)
                response = model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                data = json.loads(response.text)
                return SyntheticDataset(**data)
            except Exception as e:
                print(f"[DatasetGenerator] Gemini dataset generation failed/skipped: {e}")

        # Rule-based fallback generator
        return self._generate_fallback_dataset(domain_topic, names_sample)

    def _generate_fallback_dataset(self, domain_topic: str, names: List[Dict[str, str]]) -> SyntheticDataset:
        """High quality rule-based fallback dataset."""
        records = []
        csv_lines = ["CandidateID,CandidateName,Gender,AssessmentScore,CourseworkScore,FinalStatus"]
        
        for idx, item in enumerate(names, start=101):
            s1 = random.randint(55, 98)
            s2 = random.randint(50, 95)
            status = "Distinction" if (s1+s2)/2 >= 80 else ("Merit" if (s1+s2)/2 >= 65 else "Pass")
            rec = {
                "CandidateID": f"C{idx}",
                "CandidateName": item["name"],
                "Gender": item["gender"],
                "AssessmentScore": s1,
                "CourseworkScore": s2,
                "FinalStatus": status
            }
            records.append(rec)
            csv_lines.append(f"C{idx},{item['name']},{item['gender']},{s1},{s2},{status}")

        csv_text = "\n".join(csv_lines)
        sql_text = f"""-- SQL Schema and DDL for {domain_topic}
CREATE TABLE Candidates (
    CandidateID VARCHAR(10) PRIMARY KEY,
    CandidateName VARCHAR(100) NOT NULL,
    Gender VARCHAR(10),
    AssessmentScore INT,
    CourseworkScore INT,
    FinalStatus VARCHAR(20)
);

"""
        for r in records:
            sql_text += f"INSERT INTO Candidates VALUES ('{r['CandidateID']}', '{r['CandidateName']}', '{r['Gender']}', {r['AssessmentScore']}, {r['CourseworkScore']}, '{r['FinalStatus']}');\n"

        starter_py = f"""# ==============================================================================
# Starter Python Code for {domain_topic}
# ==============================================================================

import csv

def read_candidate_records(filename="CANDIDATES.csv"):
    candidates = []
    with open(filename, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            candidates.append({{
                "id": row["CandidateID"],
                "name": row["CandidateName"],
                "gender": row["Gender"],
                "assessment": int(row["AssessmentScore"]),
                "coursework": int(row["CourseworkScore"]),
                "status": row["FinalStatus"]
            }})
    return candidates

def calculate_average_score(candidates):
    if not candidates:
        return 0.0
    total = sum(c["assessment"] + c["coursework"] for c in candidates)
    return total / (len(candidates) * 2)

if __name__ == "__main__":
    data = read_candidate_records()
    print(f"Loaded {{len(data)}} candidate records.")
    print(f"Cohort Average: {{calculate_average_score(data):.2f}}")
"""
        return SyntheticDataset(
            title=f"{domain_topic.capitalize()} Candidate Dataset",
            description=f"Demographically balanced dataset for Cambridge assessment on {domain_topic}",
            filename="CANDIDATES.csv",
            file_type="csv",
            columns=["CandidateID", "CandidateName", "Gender", "AssessmentScore", "CourseworkScore", "FinalStatus"],
            records=records,
            csv_content=csv_text,
            sql_schema_content=sql_text,
            starter_python_code=starter_py
        )
