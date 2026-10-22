using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Cryptography;
using System.Windows.Forms;

// .NET Framework desktop application; no OCR or external packages.
public sealed class ComicDocument : IDisposable
{
    public readonly string Path;
    public readonly List<string> Pages;
    public readonly Dictionary<string, int> Turns = new Dictionary<string, int>();
    private ZipArchive archive;
    private byte[] sourceHash;

    public ComicDocument(string path)
    {
        Path = System.IO.Path.GetFullPath(path);
        OpenArchive();
        try
        {
            if (archive.Entries.Select(e => e.FullName).Distinct(StringComparer.Ordinal).Count() != archive.Entries.Count)
                throw new InvalidDataException("压缩包存在重名条目，无法安全修改。");
            Pages = archive.Entries.Where(e => IsImage(e.FullName)).Select(e => e.FullName).ToList();
            Pages.Sort(NaturalCompare);
            if (Pages.Count == 0) throw new InvalidDataException("没有找到图片页面。");
            sourceHash = HashFile(Path);
        }
        catch { Dispose(); throw; }
    }

    private void OpenArchive()
    {
        var stream = new FileStream(Path, FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete);
        try { archive = new ZipArchive(stream, ZipArchiveMode.Read, false); }
        catch { stream.Dispose(); throw; }
    }
    public static bool IsImage(string name)
    {
        return new[] { ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".avif", ".jxl" }
            .Contains(System.IO.Path.GetExtension(name).ToLowerInvariant());
    }
    private static int NaturalCompare(string a, string b)
    {
        int i = 0, j = 0;
        while (i < a.Length && j < b.Length)
        {
            if (char.IsDigit(a[i]) && char.IsDigit(b[j]))
            {
                int ai = i, bj = j;
                while (i < a.Length && char.IsDigit(a[i])) ++i;
                while (j < b.Length && char.IsDigit(b[j])) ++j;
                string an = a.Substring(ai, i - ai).TrimStart('0');
                string bn = b.Substring(bj, j - bj).TrimStart('0');
                int length = an.Length.CompareTo(bn.Length);
                if (length != 0) return length;
                int digits = String.CompareOrdinal(an, bn);
                if (digits != 0) return digits;
            }
            else
            {
                int c = char.ToUpperInvariant(a[i]).CompareTo(char.ToUpperInvariant(b[j]));
                if (c != 0) return c;
                ++i; ++j;
            }
        }
        int result = (a.Length - i).CompareTo(b.Length - j);
        return result != 0 ? result : String.CompareOrdinal(a, b);
    }
    public Bitmap Preview(string name)
    {
        using (var stream = archive.GetEntry(name).Open())
        using (var image = Image.FromStream(stream))
        {
            var bitmap = new Bitmap(image);
            int turns;
            if (Turns.TryGetValue(name, out turns)) Rotate(bitmap, turns);
            return bitmap;
        }
    }
    private static void Rotate(Image image, int turns)
    {
        if (turns == 1) image.RotateFlip(RotateFlipType.Rotate90FlipNone);
        else if (turns == 2) image.RotateFlip(RotateFlipType.Rotate180FlipNone);
        else if (turns == 3) image.RotateFlip(RotateFlipType.Rotate270FlipNone);
    }
    public void Turn(string name, int delta)
    {
        string extension = System.IO.Path.GetExtension(name).ToLowerInvariant();
        if (!new[] { ".jpg", ".jpeg", ".png", ".bmp" }.Contains(extension))
            throw new NotSupportedException("旋转支持 JPG、PNG、BMP；其他格式不会被修改。");
        int old; Turns.TryGetValue(name, out old);
        int next = (old + delta + 4) % 4;
        if (next == 0) Turns.Remove(name); else Turns[name] = next;
    }
    private static byte[] HashFile(string path)
    {
        using (var stream = File.OpenRead(path))
        using (var hash = SHA256.Create()) return hash.ComputeHash(stream);
    }
    public void SaveInPlace()
    {
        if (Turns.Count == 0) return;
        if (!sourceHash.SequenceEqual(HashFile(Path)))
            throw new IOException("原文件已被其他程序替换，请重新打开后再修改。");
        string temp = Path + ".rotating-" + Guid.NewGuid().ToString("N") + ".tmp";
        bool replaced = false;
        try
        {
            using (var file = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                using (var output = new ZipArchive(file, ZipArchiveMode.Create, true))
                {
                    foreach (var entry in archive.Entries)
                    {
                        // Retain ZIP entry order, paths and all non-image content.
                        var target = output.CreateEntry(entry.FullName, CompressionLevel.NoCompression);
                        target.LastWriteTime = entry.LastWriteTime;
                        target.ExternalAttributes = entry.ExternalAttributes;
                        using (var destination = target.Open())
                        {
                            int turns;
                            if (!Turns.TryGetValue(entry.FullName, out turns))
                            {
                                using (var original = entry.Open()) original.CopyTo(destination);
                            }
                            else
                            {
                                using (var bitmap = Preview(entry.FullName))
                                {
                                    string ext = System.IO.Path.GetExtension(entry.FullName).ToLowerInvariant();
                                    if (ext == ".jpg" || ext == ".jpeg")
                                    {
                                        var codec = ImageCodecInfo.GetImageEncoders().First(c => c.FormatID == ImageFormat.Jpeg.Guid);
                                        using (var parameters = new EncoderParameters(1))
                                        {
                                            parameters.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Quality, 98L);
                                            bitmap.Save(destination, codec, parameters);
                                        }
                                    }
                                    else bitmap.Save(destination, ext == ".png" ? ImageFormat.Png : ImageFormat.Bmp);
                                }
                            }
                        }
                    }
                }
                file.Flush(true);
            }
            if (!sourceHash.SequenceEqual(HashFile(Path)))
                throw new IOException("保存过程中原文件发生变化，未替换原文件。");
            // Same-directory replacement: no backup file, no delete-then-write gap.
            File.Replace(temp, Path, null);
            replaced = true;
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
        if (replaced)
        {
            archive.Dispose();
            Turns.Clear();
            OpenArchive();
            sourceHash = HashFile(Path);
        }
    }
    public void Dispose() { if (archive != null) archive.Dispose(); }
}

public sealed class RotatorForm : Form
{
    private ComicDocument document;
    private readonly ListBox pages = new ListBox { Dock = DockStyle.Left, Width = 245 };
    private readonly PictureBox picture = new PictureBox { Dock = DockStyle.Fill, SizeMode = PictureBoxSizeMode.Zoom, BackColor = Color.FromArgb(36, 36, 36) };
    private readonly Label status = new Label { Dock = DockStyle.Bottom, Height = 38, TextAlign = ContentAlignment.MiddleLeft };
    private readonly NumericUpDown pageNumber = new NumericUpDown { Minimum = 1, Maximum = 1, Width = 65 };
    private readonly string initialPath;
    public RotatorForm(string path)
    {
        initialPath = path;
        Text = "CBZ 单页旋转校正"; Width = 1150; Height = 850; MinimumSize = new Size(850, 600);
        Font = new Font("Microsoft YaHei UI", 10); StartPosition = FormStartPosition.CenterScreen;
        var toolbar = new FlowLayoutPanel { Dock = DockStyle.Top, Height = 80, Padding = new Padding(6), AutoScroll = true };
        AddButton(toolbar, "打开 CBZ", delegate { ChooseFile(); });
        AddButton(toolbar, "上一页", delegate { SelectPage(pages.SelectedIndex - 1); });
        AddButton(toolbar, "下一页", delegate { SelectPage(pages.SelectedIndex + 1); });
        toolbar.Controls.Add(pageNumber);
        AddButton(toolbar, "跳转", delegate { SelectPage((int)pageNumber.Value - 1); });
        AddButton(toolbar, "左转 90°", delegate { Turn(-1); });
        AddButton(toolbar, "转 180°", delegate { Turn(2); });
        AddButton(toolbar, "右转 90°", delegate { Turn(1); });
        AddButton(toolbar, "撤销本页", delegate { if (Current != null) { document.Turns.Remove(Current); RefreshPage(); } });
        AddButton(toolbar, "保存 · 直接替换", delegate { Save(); });
        Controls.Add(picture); Controls.Add(pages); Controls.Add(status); Controls.Add(toolbar);
        pages.SelectedIndexChanged += delegate { RefreshPage(); };
        AllowDrop = true;
        DragEnter += delegate(object sender, DragEventArgs e) { if (e.Data.GetDataPresent(DataFormats.FileDrop)) e.Effect = DragDropEffects.Copy; };
        DragDrop += delegate(object sender, DragEventArgs e) { var files = (string[])e.Data.GetData(DataFormats.FileDrop); if (files.Length > 0) OpenFile(files[0]); };
        FormClosing += delegate(object sender, FormClosingEventArgs e) { if (!CanLeave()) e.Cancel = true; };
        FormClosed += delegate { if (document != null) document.Dispose(); if (picture.Image != null) picture.Image.Dispose(); };
        Shown += delegate { if (!String.IsNullOrEmpty(initialPath)) OpenFile(initialPath); };
        status.Text = "打开或拖入 CBZ → 选页旋转 → 保存直接替换；不保留备份。";
    }
    private string Current { get { return document != null && pages.SelectedIndex >= 0 ? document.Pages[pages.SelectedIndex] : null; } }
    private void AddButton(FlowLayoutPanel panel, string text, Action action)
    {
        var button = new Button { Text = text, AutoSize = true, Height = 32 };
        button.Click += delegate { try { action(); } catch (Exception e) { MessageBox.Show(this, e.Message, "操作失败", MessageBoxButtons.OK, MessageBoxIcon.Error); } };
        panel.Controls.Add(button);
    }
    private void SelectPage(int index) { if (index >= 0 && index < pages.Items.Count) pages.SelectedIndex = index; }
    private bool CanLeave()
    {
        if (document == null || document.Turns.Count == 0) return true;
        var result = MessageBox.Show(this, "有未保存的旋转。是否直接替换原 CBZ？", "未保存修改", MessageBoxButtons.YesNoCancel);
        if (result == DialogResult.Cancel) return false;
        if (result == DialogResult.No) return true;
        try { Save(); return document.Turns.Count == 0; }
        catch (Exception e) { MessageBox.Show(this, e.Message, "保存失败"); return false; }
    }
    private void ChooseFile()
    {
        using (var dialog = new OpenFileDialog { Filter = "漫画压缩包 (*.cbz)|*.cbz", Title = "选择需要校正的 CBZ" })
            if (dialog.ShowDialog(this) == DialogResult.OK) OpenFile(dialog.FileName);
    }
    private void OpenFile(string path)
    {
        if (!CanLeave()) return;
        ComicDocument next;
        try { next = new ComicDocument(path); }
        catch (Exception e) { MessageBox.Show(this, e.Message, "无法打开"); return; }
        if (document != null) document.Dispose();
        document = next; pages.Items.Clear();
        for (int i = 0; i < document.Pages.Count; ++i) pages.Items.Add(String.Format("{0:D4}  {1}", i + 1, document.Pages[i]));
        pageNumber.Maximum = document.Pages.Count; SelectPage(0);
        Text = "CBZ 单页旋转校正 — " + System.IO.Path.GetFileName(path);
    }
    private void RefreshPage()
    {
        if (picture.Image != null) { picture.Image.Dispose(); picture.Image = null; }
        if (Current == null) return;
        pageNumber.Value = pages.SelectedIndex + 1;
        try
        {
            picture.Image = document.Preview(Current);
            int turns; document.Turns.TryGetValue(Current, out turns);
            status.Text = String.Format("第 {0}/{1} 页 · {2} · 旋转 {3}° · 待保存 {4} 页 · 保存直接替换，不备份",
                pages.SelectedIndex + 1, pages.Items.Count, Current, turns * 90, document.Turns.Count);
        }
        catch (Exception e) { status.Text = "无法预览该页：" + e.Message; }
    }
    private void Turn(int amount) { if (Current != null) { document.Turn(Current, amount); RefreshPage(); } }
    private void Save()
    {
        if (document == null || document.Turns.Count == 0) return;
        int count = document.Turns.Count;
        UseWaitCursor = true;
        try { document.SaveInPlace(); RefreshPage(); status.Text = "已直接替换原 CBZ，校正 " + count + " 页；未保留备份。"; }
        finally { UseWaitCursor = false; }
    }
}

public static class Program
{
    [STAThread]
    public static void Main(string[] args)
    {
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new RotatorForm(args.Length > 0 ? args[0] : null));
    }
}
