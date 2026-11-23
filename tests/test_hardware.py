"""Spec: HARDWARE — DANTE learns the PC (maker, model, motherboard, BIOS, CPU, RAM, GPU/VRAM, free disk), predicts
its resources (which local models fit, how many jobs at once) and gives a BIOS guide for auto power-on after a blackout
for this motherboard maker.
Специфікація: ЗАЛІЗО — Данте визначає ПК, прогнозує ресурси й дає інструкцію BIOS «увімкнення після зникнення світла»."""
import json
import unittest

from dante import hardware as H

RAW = {"system": {"Manufacturer": "ASUS", "Model": "System Product Name"},
       "board": {"Manufacturer": "ASUSTeK COMPUTER INC.", "Product": "PRIME B450M-A"},
       "bios": {"Manufacturer": "American Megatrends Inc.", "SMBIOSBIOSVersion": "3211"},
       "cpu": {"Name": "AMD Ryzen 5 3600 6-Core Processor", "NumberOfCores": 6, "NumberOfLogicalProcessors": 12},
       "ram_bytes": 17179869184,
       "gpus": [{"Name": "NVIDIA GeForce GT 1030", "AdapterRAM": 2147483648}],
       "vram_mb_nvidia": 2048,
       "disks": [{"DeviceID": "C:", "FreeSpace": 120 * 1024 ** 3, "Size": 476 * 1024 ** 3}]}


class ParseTest(unittest.TestCase):
    def test_summary(self):
        s = H.summarize(RAW)
        self.assertEqual(s.board_vendor, "asus")
        self.assertEqual(s.board, "PRIME B450M-A")
        self.assertEqual((s.cores, s.threads), (6, 12))
        self.assertEqual(s.ram_gb, 16)
        self.assertEqual(s.vram_gb, 2)
        self.assertEqual(s.gpu, "NVIDIA GeForce GT 1030")
        self.assertEqual(s.free_disk_gb, 120)

    def test_vendor_names(self):
        for raw, v in (("Micro-Star International Co., Ltd.", "msi"), ("Gigabyte Technology Co., Ltd.", "gigabyte"),
                       ("ASRock", "asrock"), ("Dell Inc.", "dell"), ("HP", "hp"), ("Hewlett-Packard", "hp"),
                       ("LENOVO", "lenovo"), ("Acer", "acer"), ("Some Unknown Ltd", "other")):
            self.assertEqual(H.vendor_of(raw), v, raw)

    def test_missing_fields_do_not_crash(self):
        s = H.summarize({})
        self.assertEqual(s.board_vendor, "other")
        self.assertEqual(s.ram_gb, 0)


class ForecastTest(unittest.TestCase):
    def test_models_that_fit(self):
        f = H.forecast(H.summarize(RAW))
        self.assertIn("qwen2.5-coder:3b", f.local_models)
        self.assertIn("gemma3:4b", f.local_models)          # RAM can hold it (CPU+GPU split)
        self.assertNotIn("qwen2.5-coder:32b", f.local_models)
        self.assertEqual(f.parallel_jobs, 3)                  # max(2, threads // 4)
        self.assertTrue(f.notes)

    def test_small_pc(self):
        small = dict(RAW, ram_bytes=4 * 1024 ** 3, gpus=[], vram_mb_nvidia=0,
                     cpu={"Name": "x", "NumberOfCores": 2, "NumberOfLogicalProcessors": 4})
        f = H.forecast(H.summarize(small))
        self.assertEqual(f.parallel_jobs, 2)
        self.assertNotIn("gemma3:4b", f.local_models)
        self.assertTrue(any("хмар" in n for n in f.notes))


class BiosTest(unittest.TestCase):
    def test_asus_guide(self):
        g = H.bios_power_guide("asus", "uk")
        self.assertIn("Del", g.keys)
        self.assertTrue(any("AC Power Loss" in step for step in g.steps))
        self.assertIn("Power On", " ".join(g.steps))
        self.assertTrue(g.caution)

    def test_every_vendor_has_a_guide_in_two_languages(self):
        for v in ("asus", "msi", "gigabyte", "asrock", "dell", "hp", "lenovo", "acer", "other"):
            for lang in ("uk", "en"):
                g = H.bios_power_guide(v, lang)
                self.assertTrue(g.keys and len(g.steps) >= 3 and g.caution, (v, lang))

    def test_report_text(self):
        txt = H.report(H.summarize(RAW), "uk")
        for w in ("PRIME B450M-A", "Ryzen 5 3600", "16 ГБ", "GT 1030", "BIOS", "Del"):
            self.assertIn(w, txt)


class CollectTest(unittest.TestCase):
    def test_powershell_script_asks_cim_classes(self):
        cmd = " ".join(H.collect_command())
        for c in ("Win32_ComputerSystem", "Win32_BaseBoard", "Win32_BIOS", "Win32_Processor", "Win32_VideoController",
                  "Win32_LogicalDisk", "ConvertTo-Json"):
            self.assertIn(c, cmd)

    def test_collect_uses_runner_and_parses_json(self):
        raw = H.collect(run=lambda cmd: json.dumps(RAW))
        self.assertEqual(raw["board"]["Product"], "PRIME B450M-A")


if __name__ == "__main__":
    unittest.main()
