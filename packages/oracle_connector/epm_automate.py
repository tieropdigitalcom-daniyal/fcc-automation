"""Argument construction for an installed, approved EPM Automate runtime."""
import subprocess  # nosec B404
from pathlib import Path

from .rest import OracleError


class EPMAutomate:
    def __init__(self, executable: Path, working_directory: Path, approved_jobs: set[str], verified_test=False):
        self.executable = executable.resolve(strict=True)
        self.working_directory = working_directory.resolve(strict=True)
        self.approved_jobs = approved_jobs
        self.verified_test = verified_test

    def export_data(self, job_name, filename):
        if not self.verified_test or job_name not in self.approved_jobs:
            raise OracleError("EPM Automate export requires verified non-production capability")
        return self.execute(["exportData", job_name, self.filename(filename)])

    def download_file(self, filename):
        return self.execute(["downloadFile", self.filename(filename)])

    @staticmethod
    def filename(filename):
        if Path(filename).name != filename or any(char in filename for char in "\\/:\r\n"):
            raise ValueError("An explicit repository basename is required")
        return filename

    def execute(self, arguments):
        if not self.verified_test:
            raise OracleError("EPM Automate capabilities are unverified")
        # Credentials are supplied by an externally established encrypted OAuth session.
        output = subprocess.run([str(self.executable), *arguments], cwd=self.working_directory,
                                capture_output=True, timeout=300, shell=False, check=False)  # nosec B603
        if output.returncode:
            raise OracleError("EPM Automate command failed; inspect protected operator logs")
        return {"returncode": output.returncode, "command": arguments[0]}
