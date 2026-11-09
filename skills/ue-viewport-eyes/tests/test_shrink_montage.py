"""Pruebas de scripts/shrink-montage.ps1. Necesita Windows PowerShell + System.Drawing, sin Unreal, sin red."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "shrink-montage.ps1")
PS = shutil.which("powershell")


def ps(command):
    return subprocess.run([PS, "-NoProfile", "-NonInteractive", "-Command", command],
                          capture_output=True, text=True)


def run_montage(*args):
    return subprocess.run([PS, "-NoProfile", "-NonInteractive", "-File", SCRIPT, *args],
                          capture_output=True, text=True)


@unittest.skipUnless(PS and sys.platform == "win32", "needs Windows PowerShell")
class ShrinkMontage(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="eyes_")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def make_png(self, name, w=1280, h=720):
        path = os.path.join(self.dir, name)
        r = ps("Add-Type -AssemblyName System.Drawing; "
               "$b = New-Object System.Drawing.Bitmap %d, %d; $b.Save('%s', "
               "[System.Drawing.Imaging.ImageFormat]::Png); $b.Dispose()" % (w, h, path))
        self.assertEqual(r.returncode, 0, r.stderr)
        return path

    def size_of(self, path):
        r = ps("Add-Type -AssemblyName System.Drawing; "
               "$i = [System.Drawing.Image]::FromFile('%s'); "
               "Write-Output ($i.Width.ToString() + 'x' + $i.Height.ToString()); $i.Dispose()" % path)
        return r.stdout.strip()

    def test_three_images_make_1280x720(self):
        imgs = [self.make_png(n) for n in ("front.png", "tq.png", "side.png")]
        out = os.path.join(self.dir, "out", "montage.jpg")
        r = run_montage("-Images", ",".join(imgs), "-OutFile", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("MONTAJE 1280x720", r.stdout)
        self.assertTrue(os.path.isfile(out))
        self.assertEqual(self.size_of(out), "1280x720")

    def test_missing_image_fails_with_clear_message(self):
        good = self.make_png("front.png")
        out = os.path.join(self.dir, "montage.jpg")
        r = run_montage("-Images", good + "," + os.path.join(self.dir, "no-existe.png"),
                        "-OutFile", out)
        self.assertEqual(r.returncode, 1)
        self.assertIn("FALTA", r.stderr)
        self.assertNotIn("MONTAJE", r.stdout)
        self.assertFalse(os.path.exists(out))

    def test_all_paths_bad_fails(self):
        out = os.path.join(self.dir, "montage.jpg")
        r = run_montage("-Images", os.path.join(self.dir, "a.png"), "-OutFile", out)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("MONTAJE", r.stdout)

    def test_corrupt_image_fails(self):
        bad = os.path.join(self.dir, "bad.png")
        with open(bad, "wb") as f:
            f.write(b"not an image")
        out = os.path.join(self.dir, "montage.jpg")
        r = run_montage("-Images", bad, "-OutFile", out)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("MONTAJE", r.stdout)


if __name__ == "__main__":
    unittest.main()
