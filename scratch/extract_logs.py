import subprocess

res = subprocess.run(['docker', 'logs', '--timestamps', 'bug_reproduction_worker'], capture_output=True)
stdout_text = res.stdout.decode('utf-8', errors='replace')
stderr_text = res.stderr.decode('utf-8', errors='replace')

lines = stdout_text.splitlines() + stderr_text.splitlines()
in_window = False
matched_lines = []

for line in lines:
    if '2026-09-09T10:21:0' in line or '2026-09-09 10:21:0' in line or ('2026-09-09' in line and '10:21:1' in line):
        in_window = True
    if in_window:
        matched_lines.append(line)
        if '2026-09-09T10:27:12' in line or '2026-09-09 10:27:12' in line:
            break

with open('scratch/worker_1021_1027.log', 'w', encoding='utf-8') as f:
    f.write('\n'.join(matched_lines))

print(f"Extracted {len(matched_lines)} lines to scratch/worker_1021_1027.log")
