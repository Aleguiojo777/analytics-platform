using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

namespace DataLensLauncher
{
    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            string appDir = AppDomain.CurrentDomain.BaseDirectory;
            string scriptPath = Path.Combine(appDir, "run-datalens.bat");

            if (!File.Exists(scriptPath))
            {
                MessageBox.Show(
                    "run-datalens.bat was not found next to DataLens.exe. Extract the full DataLens ZIP, then run DataLens.exe again.",
                    "DataLens",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return;
            }

            try
            {
                ProcessStartInfo startInfo = new ProcessStartInfo
                {
                    FileName = scriptPath,
                    WorkingDirectory = appDir,
                    UseShellExecute = true
                };
                Process.Start(startInfo);
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "DataLens could not start. " + ex.Message,
                    "DataLens",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }
    }
}
