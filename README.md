# EAPS — Energy-Aware Preemptive Scheduler

This repository contains a complete CPU scheduling simulator focused on **reducing energy consumption without compromising performance**, designed for **mobile and embedded systems**.  
It includes an interactive GUI, real-time visualizations, and a batch-experiment engine.

---

## ⭐ Key Features
- **Deadline-Safe Energy-Aware Scheduler (EAPSS)**  
  Chooses the *minimum* CPU frequency and core count that can meet all task deadlines using fast feasibility checks.

- **Baseline Performance-First Scheduler**  
  Always runs at max frequency/cores for comparison.

- **Dynamic Voltage/Frequency Scaling (DVFS)**  
  Simulated with selectable frequency levels.

- **Real-time GUI (Tkinter + Matplotlib)**  
  - Live energy graph  
  - CPU frequency timeline  
  - Active cores timeline  
  - Utilization graph  
  - Gantt-like running-task view  

- **Workload Generator**  
  Randomized task sets with WCET, arrival times, and deadlines (light, bursty, heavy patterns).

- **Batch Runner**  
  Automatically runs 5× seeds across both schedulers and exports:
  - CSV results  
  - Per-run energy graphs  

---

## 🧠 Algorithm Summary — Deadline-Safe DVFS Scheduler
The scheduler minimizes power while ensuring performance using:

### 1. **Feasibility check**
For each possible (freq, cores) pair:
- Estimate if all ready tasks can meet their deadlines.
- If infeasible, skip it.
- Select the configuration with **lowest estimated energy**.

### 2. **Execution**
- Sorted-by-deadline execution (EDF-like).
- Distributes available CPU cycles across ready tasks.
- Updates remaining WCET and logs stats.

### 3. **Energy Model**
```
Power ∝ freq³ × cores
```
A realistic approximation for mobile SoCs.

### 4. **Fallback to Max Performance**
If no feasible energy-efficient configuration exists, the scheduler jumps to full power to avoid deadline misses.

---

## 📂 File Overview
```
cpu_simulator_fixed.py
├── DeadlineSafeStepper      # Energy-aware DVFS scheduler
├── PerformanceFirstStepper  # Max-performance baseline
├── Workload generator       # Light/bursty/heavy tasks
├── Power & frequency model
├── Tkinter GUI with plots
└── Batch run system (CSV + graphs)
```

---

## 🚀 How to Run
```bash
python3 cpu_simulator_fixed.py
```

---

## 📊 Batch Mode Output
Generates:

### CSV Columns:
- scheduler  
- seed  
- energy  
- tasks  
- missed  

### Graphs:
Per-seed energy curves (PNG).

---

## 🛠 Suitable For
- Research on DVFS scheduling  
- Testing real-time energy constraints  
- Embedded/mobile system algorithm prototyping  
- Academic demonstrations & coursework  

---

## ✨ Credits
Developed as an experimental platform for comparing **energy-aware CPU scheduling strategies** against performance-oriented baselines.

