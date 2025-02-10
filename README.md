# 🚗 Parking Lot Detection
## 📌 Overview  
This repository contains an intelligent parking system that detects **occupied and free parking spots** using a **finetuned YOLO11x model**. The system **visualizes** real-time parking occupancy and dynamically updates pricing based on demand.

<img width="1396" alt="image" src="https://github.com/user-attachments/assets/33b5e9d5-40ca-42d4-b34c-eb869cdf1504" />

---

## 📋 Instructions  

### 1️⃣ Clone the repository  
```bash
git clone https://github.com/digital-business-lab/ParkingLotDetection.git
```

### 2️⃣ Install libraries
```bash
pip install torch torchvision torchaudio websockets opencv-python numpy mss ultralytics sqlite3
```

### 3️⃣ Run the detection system
Navigate to the directory where your finetuned YOLO model is located:
```bash
cd User/FolderWithFintuned11x.pt
```
Then run the script:
```bash
python ParkingLotDetection.py
```
✅ Vehicle detection is running!

### 4️⃣ Open the web interface
Open the ParkingLot.html file in a browser to view the real-time parking occupancy visualization.

🚗 Your system is now running and you can monitor parking occupancy in real-time!

---

## ⚙️ How it works

	1.	The system uses a finetuned YOLO11x for vehicle detection
	2.	Predefined parking zones are compared against detected bounding boxes
	3.	Parking data is stored in an SQLite database
	4.	A WebSocket server updates occupancy and pricing dynamically
	5.	Dynamic pricing adjusts based on total occupancy and historical parking durations
	6.	The web interface provides a live visualization of the parking space status (🔴 occupied / 🟢 free)
 		and the dynamic pricing


Feel free to contribute or raise an issue if you encounter any problems! 🚀

