using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Windows.Forms;

public static class RotatorTests
{
    private static void Check(bool value, string message) { if (!value) throw new Exception(message); }
    private static byte[] Bytes(ZipArchive archive, string name)
    {
        using (var memory = new MemoryStream()) { using (var stream = archive.GetEntry(name).Open()) stream.CopyTo(memory); return memory.ToArray(); }
    }
    [STAThread]
    public static int Main(string[] args)
    {
        if (args.Length == 2)
        {
            Application.EnableVisualStyles();
            var flags = BindingFlags.NonPublic | BindingFlags.Instance;
            using (var form = new RotatorForm(null))
            {
                form.Opacity = 0; form.ShowInTaskbar = false;
                form.Show(); Application.DoEvents();
                typeof(RotatorForm).GetMethod("OpenFile", flags).Invoke(form, new object[] { args[0] });
                typeof(RotatorForm).GetMethod("SelectPage", flags).Invoke(form, new object[] { 6 });
                var picture = (PictureBox)typeof(RotatorForm).GetField("picture", flags).GetValue(form);
                int width = picture.Image.Width, height = picture.Image.Height;
                typeof(RotatorForm).GetMethod("Turn", flags).Invoke(form, new object[] { 1 });
                Check(picture.Image.Width == height && picture.Image.Height == width, "real page preview rotation");
                var label = (Label)typeof(RotatorForm).GetField("status", flags).GetValue(form);
                Check(label.Text.Contains("第 7/") && label.Text.Contains("旋转 90°"), "real page number/status");
                using (var rendering = new Bitmap(form.Width, form.Height))
                {
                    form.DrawToBitmap(rendering, new Rectangle(0, 0, form.Width, form.Height));
                    rendering.Save(args[1], ImageFormat.Png);
                }
                var document = (ComicDocument)typeof(RotatorForm).GetField("document", flags).GetValue(form);
                document.Turns.Clear(); form.Close();
                Console.WriteLine("PASS: actual CBZ page 7, 90-degree preview and UI render; source not saved.");
            }
            return 0;
        }
        string directory = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "cbz-rotation-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            string path = System.IO.Path.Combine(directory, "test.cbz");
            using (var archive = ZipFile.Open(path, ZipArchiveMode.Create))
            {
                foreach (var name in new[] { "10.bmp", "2.jpg", "1.png" })
                {
                    using (var image = new Bitmap(60, 90))
                    {
                        using (var g = Graphics.FromImage(image)) g.Clear(Color.White);
                        image.SetPixel(0, 0, Color.Red); image.SetPixel(59, 0, Color.Blue);
                        var entry = archive.CreateEntry(name); entry.LastWriteTime = new DateTimeOffset(2025, 1, 2, 3, 4, 6, TimeSpan.Zero);
                        using (var stream = entry.Open()) image.Save(stream, name.EndsWith("png") ? ImageFormat.Png : name.EndsWith("jpg") ? ImageFormat.Jpeg : ImageFormat.Bmp);
                    }
                }
                using (var writer = new StreamWriter(archive.CreateEntry("ComicInfo.xml").Open())) writer.Write("<ComicInfo><Title>test</Title></ComicInfo>");
            }
            byte[] jpeg, metadata; string[] order;
            using (var archive = ZipFile.OpenRead(path)) { jpeg = Bytes(archive, "2.jpg"); metadata = Bytes(archive, "ComicInfo.xml"); order = archive.Entries.Select(e => e.FullName).ToArray(); }
            using (var document = new ComicDocument(path))
            {
                Check(document.Pages.SequenceEqual(new[] { "1.png", "2.jpg", "10.bmp" }), "natural page order");
                document.Turn("1.png", 1);
                using (var preview = document.Preview("1.png"))
                {
                    Check(preview.Width == 90 && preview.Height == 60, "90 degree dimensions");
                    Check(preview.GetPixel(89, 0).ToArgb() == Color.Red.ToArgb(), "90 degree direction");
                }
                document.SaveInPlace(); Check(document.Turns.Count == 0, "save consumes pending rotations");
                using (var archive = ZipFile.OpenRead(path))
                {
                    Check(jpeg.SequenceEqual(Bytes(archive, "2.jpg")), "untouched JPEG bytes preserved");
                    Check(metadata.SequenceEqual(Bytes(archive, "ComicInfo.xml")), "metadata preserved");
                    Check(order.SequenceEqual(archive.Entries.Select(e => e.FullName)), "ZIP order preserved");
                    Check(archive.GetEntry("1.png").LastWriteTime.Year == 2025, "timestamp preserved");
                }
                using (var saved = document.Preview("1.png")) Check(saved.Width == 90 && saved.Height == 60, "reopened corrected image");
                byte[] noChange = File.ReadAllBytes(path);
                for (int n = 0; n < 4; ++n) document.Turn("2.jpg", 1);
                document.SaveInPlace(); Check(noChange.SequenceEqual(File.ReadAllBytes(path)), "four turns are byte-exact no-op");
                document.Turn("2.jpg", -1); document.Turn("10.bmp", 2); document.SaveInPlace();
                using (var rotated = document.Preview("2.jpg")) Check(rotated.Width == 90 && rotated.Height == 60, "JPEG re-encode supported");
                using (var rotated = document.Preview("10.bmp")) Check(rotated.GetPixel(59, 89).ToArgb() == Color.Red.ToArgb(), "BMP 180 direction");
                Check(Directory.GetFiles(directory).Length == 1, "no backup or temporary files retained");
            }
            using (var document = new ComicDocument(path))
            {
                document.Turn("1.png", 1);
                string replacement = System.IO.Path.Combine(directory, "external.tmp");
                File.WriteAllText(replacement, "external replacement"); File.Replace(replacement, path, null);
                bool refused = false;
                try { document.SaveInPlace(); } catch (IOException) { refused = true; }
                Check(refused && File.ReadAllText(path) == "external replacement", "external changes refuse overwrite");
                Check(Directory.GetFiles(directory).Length == 1, "refused save leaves no backup/temp");
            }
            Console.WriteLine("PASS: natural ordering; PNG/JPEG/BMP rotation; unchanged entry bytes/order/metadata; atomic replacement; no backup; stale source refusal.");
            return 0;
        }
        catch (Exception e) { Console.Error.WriteLine(e); return 1; }
        finally { Directory.Delete(directory, true); }
    }
}
