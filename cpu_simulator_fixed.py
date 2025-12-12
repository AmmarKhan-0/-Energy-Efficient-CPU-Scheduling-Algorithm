#!/usr/bin/env python3
"""
cpu_simulator_fixed.py

- Deadline-Safe (energy-aware) scheduler
- Performance-First (max-performance) baseline
- Tkinter GUI with Matplotlib animation
- Gantt bar, energy/freq/cores/util plots
- Non-blocking Batch Run (CSV + per-run graphs), folder selectable
- Fixes Matplotlib FuncAnimation warning (cache_frame_data=False)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import random
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from copy import deepcopy
import csv
import os

# -----------------------
# Simulation parameters
# -----------------------
FREQ_LEVELS = [0.4, 0.6, 0.8, 1.0]
MAX_CORES = 4
PERF_CONSTANT = 2000        # cycles-per-ms-per-core at freq=1.0 (arbitrary scale)
K_POWER = 1.2
DT = 0.05                   # simulation step (s)
SIM_DURATION = 8.0

# -----------------------
# Task model + workload
# -----------------------
class Task:
    def __init__(self, tid, wcet_sec, arrival, deadline):
        self.tid = tid
        self.wcet = wcet_sec
        self.arrival = arrival
        self.deadline = deadline
        self.remaining = wcet_sec
        self.start_time = None
        self.finish_time = None

    def is_ready(self, now): return (self.arrival <= now) and (self.remaining > 1e-12)
    def is_done(self): return self.remaining <= 1e-12

def generate_workload(seed=1, n=30):
    random.seed(seed)
    tasks = []
    for i in range(n):
        typ = random.choices(["light", "bursty", "heavy"], weights=[0.45,0.35,0.2])[0]
        arrival = round(random.uniform(0, SIM_DURATION*0.8), 3)
        if typ == "light":
            wcet = random.uniform(0.05, 0.3)
            deadline = arrival + random.uniform(0.8, 2.0)
        elif typ == "bursty":
            wcet = random.uniform(0.1, 0.4)
            deadline = arrival + random.uniform(0.2, 0.8)
        else:
            wcet = random.uniform(0.6, 1.6)
            deadline = arrival + random.uniform(1.0, 3.0)
        tasks.append(Task(i+1, wcet, arrival, deadline))
    tasks.sort(key=lambda t: t.arrival)
    # ensure at least one task at t=0 to make GUI show activity quickly
    if tasks and tasks[0].arrival > 0:
        tasks[0].arrival = 0.0
    return tasks

# -----------------------
# Utility functions
# -----------------------
def cycles_per_second(freq_frac, cores):
    return freq_frac * PERF_CONSTANT * cores * 1000.0

def power_for(freq_frac, cores):
    return K_POWER * (freq_frac ** 3) * cores

# -----------------------
# Scheduler steppers
# -----------------------
class DeadlineSafeStepper:
    def __init__(self, tasks):
        self.tasks = deepcopy(tasks)
        self.now = 0.0
        self.freq = max(FREQ_LEVELS)
        self.cores = MAX_CORES
        self.energy = 0.0
        self.history = {"t":[], "energy":[], "freq":[], "cores":[], "util":[], "running_task":[]}

    def runnable(self):
        return [t for t in self.tasks if t.is_ready(self.now)]

    def feasibility_check(self, cand_freq, cand_cores):
        for t in self.runnable():
            time_needed = t.remaining / (cand_cores * cand_freq if cand_cores*cand_freq>0 else 1e-9)
            if self.now + time_needed > t.deadline + 1e-9:
                return False
        return True

    def choose_config(self):
        best = None
        for f in FREQ_LEVELS:
            for n in range(1, MAX_CORES+1):
                if not self.feasibility_check(f, n): 
                    continue
                energy_est = power_for(f, n) * DT
                if best is None or energy_est < best[2]:
                    best = (f, n, energy_est)
        if best is None:
            # fallback to max perf to make progress
            return max(FREQ_LEVELS), MAX_CORES
        return best[0], best[1]

    def step(self, dt=DT):
        # stop condition: all done or time exceeded
        if all(t.is_done() for t in self.tasks) or self.now >= SIM_DURATION:
            return False

        f, n = self.choose_config()
        self.freq, self.cores = f, n

        runnable = sorted(self.runnable(), key=lambda t: (t.deadline if t.deadline is not None else 1e9))
        cap = cycles_per_second(self.freq, self.cores) * dt
        running_tid = None
        work_done = 0.0

        for t in runnable:
            if cap <= 0: break
            cap_sec = cap / (PERF_CONSTANT * 1000.0)
            do = min(t.remaining, cap_sec)
            if do <= 0:
                do = min(1e-6, t.remaining)  # small progress guard
            if t.start_time is None and do > 0:
                t.start_time = self.now
            t.remaining -= do
            work_done += do
            running_tid = t.tid
            cap -= do * (PERF_CONSTANT * 1000.0)
            if t.is_done():
                t.finish_time = self.now + dt
            if cap <= 0: break

        p = power_for(self.freq, self.cores)
        self.energy += p * dt
        self.now += dt
        util = (work_done / (self.cores * self.freq * dt)) if (self.cores * self.freq * dt) > 0 else 0.0

        self.history["t"].append(self.now)
        self.history["energy"].append(self.energy)
        self.history["freq"].append(self.freq)
        self.history["cores"].append(self.cores)
        self.history["util"].append(util)
        self.history["running_task"].append(running_tid)

        return not (all(t.is_done() for t in self.tasks) or self.now >= SIM_DURATION)

class PerformanceFirstStepper:
    def __init__(self, tasks):
        self.tasks = deepcopy(tasks)
        self.now = 0.0
        self.freq = max(FREQ_LEVELS)
        self.cores = MAX_CORES
        self.energy = 0.0
        self.history = {"t":[], "energy":[], "freq":[], "cores":[], "util":[], "running_task":[]}

    def runnable(self):
        return [t for t in self.tasks if t.is_ready(self.now)]

    def choose_config(self):
        return max(FREQ_LEVELS), MAX_CORES

    def step(self, dt=DT):
        if all(t.is_done() for t in self.tasks) or self.now >= SIM_DURATION:
            return False

        self.freq, self.cores = self.choose_config()
        runnable = sorted(self.runnable(), key=lambda t: (t.deadline if t.deadline is not None else 1e9))
        cap = cycles_per_second(self.freq, self.cores) * dt
        running_tid = None
        work_done = 0.0

        for t in runnable:
            if cap <= 0: break
            cap_sec = cap / (PERF_CONSTANT * 1000.0)
            do = min(t.remaining, cap_sec)
            if do <= 0:
                do = min(1e-6, t.remaining)
            if t.start_time is None and do > 0:
                t.start_time = self.now
            t.remaining -= do
            work_done += do
            running_tid = t.tid
            cap -= do * (PERF_CONSTANT * 1000.0)
            if t.is_done():
                t.finish_time = self.now + dt
            if cap <= 0: break

        p = power_for(self.freq, self.cores)
        self.energy += p * dt
        self.now += dt
        util = (work_done / (self.cores * self.freq * dt)) if (self.cores * self.freq * dt) > 0 else 0.0

        self.history["t"].append(self.now)
        self.history["energy"].append(self.energy)
        self.history["freq"].append(self.freq)
        self.history["cores"].append(self.cores)
        self.history["util"].append(util)
        self.history["running_task"].append(running_tid)

        return not (all(t.is_done() for t in self.tasks) or self.now >= SIM_DURATION)

# -----------------------
# GUI + animation + batch
# -----------------------
class CPUSimApp:
    def __init__(self, master):
        self.master = master
        master.title("EAPSS CPU Scheduler Simulator")

        # Controls frame
        ctrl = ttk.Frame(master)
        ctrl.pack(side=tk.TOP, fill=tk.X, padx=6, pady=6)

        ttk.Label(ctrl, text="Scheduler:").grid(row=0, column=0, sticky=tk.W)
        self.sched_var = tk.StringVar(value="Deadline-Safe")
        ttk.Combobox(ctrl, textvariable=self.sched_var, values=["Deadline-Safe", "Performance-First"], width=20).grid(row=0, column=1, sticky=tk.W)

        ttk.Label(ctrl, text="Seed:").grid(row=0, column=2, sticky=tk.W, padx=(8,0))
        self.seed_var = tk.IntVar(value=1)
        ttk.Entry(ctrl, textvariable=self.seed_var, width=6).grid(row=0, column=3, sticky=tk.W)

        ttk.Label(ctrl, text="Speed x:").grid(row=0, column=4, sticky=tk.W, padx=(8,0))
        self.speed_var = tk.DoubleVar(value=1.0)
        ttk.Scale(ctrl, variable=self.speed_var, from_=0.25, to=4.0, orient=tk.HORIZONTAL, length=140).grid(row=0, column=5, sticky=tk.W)

        self.start_btn = ttk.Button(ctrl, text="Start", command=self.start)
        self.start_btn.grid(row=0, column=6, padx=6)
        self.pause_btn = ttk.Button(ctrl, text="Pause", command=self.pause, state=tk.DISABLED)
        self.pause_btn.grid(row=0, column=7)
        self.reset_btn = ttk.Button(ctrl, text="Reset", command=self.reset, state=tk.DISABLED)
        self.reset_btn.grid(row=0, column=8, padx=6)

        self.batch_btn = ttk.Button(ctrl, text="Batch Run (5 seeds)", command=self.batch_run)
        self.batch_btn.grid(row=0, column=9, padx=6)

        # Status label
        self.status_label = ttk.Label(master, text="Ready")
        self.status_label.pack(side=tk.TOP, fill=tk.X, padx=6)

        # Figure and axes
        self.fig, self.axs = plt.subplots(4, 1, figsize=(8, 9))
        plt.tight_layout()
        # Create Gantt axes once
        self.gantt_ax = self.fig.add_axes([0.12, 0.02, 0.76, 0.06])
        self.gantt_ax.set_xlim(0, SIM_DURATION)
        self.gantt_ax.set_ylim(0, 1)
        self.gantt_ax.set_yticks([])
        self.gantt_ax.set_xlabel("Time (s)")

        self.canvas = FigureCanvasTkAgg(self.fig, master=master)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

        # internal
        self.stepper = None
        self.ani = None
        self.running = False

        self._init_plots()

    def _init_plots(self):
        for ax in self.axs:
            ax.clear(); ax.grid(True)
        self.axs[0].set_title("Cumulative Energy (J)")
        self.axs[1].set_title("CPU Frequency (frac)")
        self.axs[2].set_title("Active Cores")
        self.axs[3].set_title("Utilization (est)")
        # clear gantt
        self.gantt_ax.cla()
        self.gantt_ax.set_xlim(0, SIM_DURATION)
        self.gantt_ax.set_ylim(0,1)
        self.gantt_ax.set_yticks([])
        self.gantt_ax.set_xlabel("Time (s)")
        self.canvas.draw()

    def start(self):
        if self.running:
            return
        self.running = True
        self.start_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL)
        self.reset_btn.config(state=tk.DISABLED)
        self.batch_btn.config(state=tk.DISABLED)

        seed = int(self.seed_var.get())
        sched = self.sched_var.get()
        tasks = generate_workload(seed=seed, n=30)
        if sched == "Deadline-Safe":
            self.stepper = DeadlineSafeStepper(tasks)
        else:
            self.stepper = PerformanceFirstStepper(tasks)

        # FuncAnimation with cache_frame_data=False to silence the warning
        self.ani = FuncAnimation(self.fig, self._update_frame, interval=50, blit=False, cache_frame_data=False)
        self.status_label.config(text=f"Running ({sched})")

    def pause(self):
        if not self.running:
            return
        self.running = False
        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED)
        self.reset_btn.config(state=tk.NORMAL)
        self.batch_btn.config(state=tk.NORMAL)
        if self.ani:
            self.ani.event_source.stop()
        self.status_label.config(text="Paused")

    def reset(self):
        if self.ani:
            self.ani.event_source.stop()
            self.ani = None
        self.stepper = None
        self.running = False
        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED)
        self.reset_btn.config(state=tk.DISABLED)
        self.batch_btn.config(state=tk.NORMAL)
        self._init_plots()
        self.status_label.config(text="Reset / Ready")

    def _update_frame(self, frame):
        # run several logical steps depending on speed
        if self.stepper is None:
            return

        speed = float(self.speed_var.get())
        steps = max(1, int(round(speed)))
        cont = True
        for _ in range(steps):
            cont = self.stepper.step(DT)
            if not cont:
                break

        hist = self.stepper.history
        t = np.array(hist["t"])
        if t.size == 0:
            # still no data to plot
            return

        energy = np.array(hist["energy"])
        freq = np.array(hist["freq"])
        cores = np.array(hist["cores"])
        util = np.array(hist["util"])
        running = hist["running_task"]

        # update plots
        self.axs[0].cla(); self.axs[0].plot(t, energy, color='tab:blue'); self.axs[0].set_ylabel("Energy (J)"); self.axs[0].grid(True)
        self.axs[1].cla(); self.axs[1].step(t, freq, where='post', color='tab:orange'); self.axs[1].set_ylabel("Freq"); self.axs[1].grid(True)
        self.axs[2].cla(); self.axs[2].step(t, cores, where='post', color='tab:green'); self.axs[2].set_ylabel("Cores"); self.axs[2].grid(True)
        self.axs[3].cla(); self.axs[3].plot(t, util, color='tab:red'); self.axs[3].set_ylabel("Util"); self.axs[3].grid(True)
        self.axs[3].set_xlabel("Time (s)")

        # update gantt (reuse single axes)
        self.gantt_ax.cla()
        self.gantt_ax.set_xlim(0, SIM_DURATION)
        self.gantt_ax.set_ylim(0, 1)
        self.gantt_ax.set_yticks([])
        last_running = running[-1]
        last_t = t[-1]
        if last_running is not None:
            self.gantt_ax.broken_barh([(max(0, last_t - DT), DT)], (0.2, 0.6), facecolors=('tab:purple'))
            self.gantt_ax.text(last_t, 0.5, f"Task: {last_running}", va='center', ha='left')
        else:
            self.gantt_ax.text(0.5, 0.5, "Idle", va='center', ha='center')

        # stats to show
        total_tasks = len(self.stepper.tasks)
        missed = sum(1 for tsk in self.stepper.tasks if (tsk.deadline is not None and ((tsk.finish_time is not None and tsk.finish_time > tsk.deadline) or (not tsk.is_done() and self.stepper.now > tsk.deadline))))
        if not cont:
            # finished
            if self.ani:
                self.ani.event_source.stop()
            self.running = False
            self.status_label.config(text=f"Done — Energy={self.stepper.energy:.3f}J | Tasks={total_tasks} | Missed={missed}")
            self.start_btn.config(state=tk.NORMAL)
            self.pause_btn.config(state=tk.DISABLED)
            self.reset_btn.config(state=tk.NORMAL)
            self.batch_btn.config(state=tk.NORMAL)

        self.canvas.draw()

    # -----------------------
    # Batch run (non-blocking)
    # -----------------------
    def batch_run(self):
        # ask user where to save CSV and graphs folder
        save_csv = filedialog.asksaveasfilename(defaultextension=".csv", title="Save batch CSV as")
        if not save_csv:
            return
        graphs_dir = filedialog.askdirectory(title="Select folder to save batch graphs (will create subfolder 'batch_graphs' if not present)")
        if not graphs_dir:
            return
        # disable UI controls while running
        self.batch_btn.config(state=tk.DISABLED)
        self.start_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.DISABLED)
        self.reset_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Running batch (this may take a little while)...")

        def run_batch_thread():
            schedulers = ["Deadline-Safe", "Performance-First"]
            n_tests = 5
            results = []
            graphs_out = os.path.join(graphs_dir, "batch_graphs")
            os.makedirs(graphs_out, exist_ok=True)

            for sched in schedulers:
                for seed in range(1, n_tests+1):
                    tasks = generate_workload(seed=seed, n=30)
                    stepper = DeadlineSafeStepper(tasks) if sched == "Deadline-Safe" else PerformanceFirstStepper(tasks)
                    # run to completion (fast, non-GUI)
                    while stepper.step(DT):
                        pass
                    total_tasks = len(stepper.tasks)
                    missed = sum(1 for t in stepper.tasks if (t.deadline is not None and ((t.finish_time is not None and t.finish_time > t.deadline) or (not t.is_done() and stepper.now > t.deadline))))
                    energy = stepper.energy
                    results.append({"scheduler":sched, "seed":seed, "energy":energy, "tasks":total_tasks, "missed":missed})

                    # save per-run energy plot
                    try:
                        plt.figure(figsize=(6,4))
                        plt.plot(stepper.history["t"], stepper.history["energy"], label="Cumulative Energy")
                        plt.xlabel("Time (s)")
                        plt.ylabel("Energy (J)")
                        plt.title(f"{sched} (seed={seed})")
                        plt.grid(True)
                        outname = os.path.join(graphs_out, f"{sched.replace(' ','_')}_seed{seed}.png")
                        plt.savefig(outname)
                        plt.close()
                    except Exception as e:
                        print("Warning: failed to save graph:", e)

            # write CSV
            try:
                with open(save_csv, "w", newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=["scheduler","seed","energy","tasks","missed"])
                    writer.writeheader()
                    writer.writerows(results)
            except Exception as e:
                print("Failed to write CSV:", e)

            # re-enable UI (on main thread)
            def finish_ui():
                self.batch_btn.config(state=tk.NORMAL)
                self.start_btn.config(state=tk.NORMAL)
                self.reset_btn.config(state=tk.NORMAL)
                self.status_label.config(text=f"Batch done — CSV saved to: {os.path.basename(save_csv)}. Graphs in {graphs_out}")
                messagebox.showinfo("Batch Run", f"Batch finished.\nCSV: {save_csv}\nGraphs: {graphs_out}")

            self.master.after(50, finish_ui)

        t = threading.Thread(target=run_batch_thread, daemon=True)
        t.start()

# -----------------------
# Run
# -----------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = CPUSimApp(root)
    root.mainloop()
