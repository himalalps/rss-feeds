import logging
import os
import subprocess
import sys

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def run_all_feeds():
    """Run all Python scripts in the feed_generators directory.

    Returns:
        int: Exit code (0 for success, 1 if any script failed)
    """
    feed_generators_dir = os.path.dirname(os.path.abspath(__file__))
    skip_scripts = []
    optional_scripts = {"tencent_hy_research_blog.py"}
    failed_scripts = []
    optional_failed_scripts = []
    successful_scripts = []

    for filename in os.listdir(feed_generators_dir):
        if filename.endswith("blog.py") and filename != os.path.basename(__file__):
            if filename in skip_scripts:
                logger.info(f"Skipping script: {filename}")
                continue

            script_path = os.path.join(feed_generators_dir, filename)
            logger.info(f"Running script: {script_path}")
            result = subprocess.run(
                ["python", script_path], capture_output=True, text=True
            )
            if result.returncode == 0:
                logger.info(f"Successfully ran script: {script_path}")
                successful_scripts.append(filename)
            elif filename in optional_scripts:
                logger.warning(
                    f"Optional feed failed; keeping its existing XML: "
                    f"{script_path}\n{result.stderr}"
                )
                optional_failed_scripts.append(filename)
            else:
                logger.error(f"Error running script: {script_path}\n{result.stderr}")
                failed_scripts.append(filename)

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info(f"Feed Generation Summary:")
    logger.info(f"  Successful: {len(successful_scripts)}")
    logger.info(f"  Optional failures: {len(optional_failed_scripts)}")
    logger.info(f"  Failed: {len(failed_scripts)}")

    if successful_scripts:
        logger.info(f"\nSuccessful feeds:")
        for script in successful_scripts:
            logger.info(f"  ✓ {script}")

    if optional_failed_scripts:
        logger.warning(f"\nOptional feeds using existing XML:")
        for script in optional_failed_scripts:
            logger.warning(f"  ! {script}")

    if failed_scripts:
        logger.error(f"\nFailed feeds:")
        for script in failed_scripts:
            logger.error(f"  ✗ {script}")
        logger.error(f"\nERROR: {len(failed_scripts)} feed(s) failed to generate")
        return 1

    logger.info(f"{'='*60}\n")
    return 0


if __name__ == "__main__":
    exit_code = run_all_feeds()
    sys.exit(exit_code)
