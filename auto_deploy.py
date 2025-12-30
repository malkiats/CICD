"""This module automates the deployment process and handling deployment checks."""

import argparse
import logging
import time
from typing import Any, Dict

import requests
from github import GithubException
from lapwing_core.ghub import LapwingGitHubClient, LapwingRepository
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class DeployInputs(BaseSettings):
    """
    The environment settings for the script.
    """

    token: str = Field(default="")
    repo_owner: str = Field(default="")
    repo_name: str = Field(default="")
    release_tag: str = Field(default="")
    bot_token: str = Field(default="")
    local_repo_owner: str = Field(default="")
    local_repo_name: str = Field(default="")
    prod_env_file_path: str = Field(default="")
    pre_prod_env_file_path: str = Field(default="")
    
    model_config = SettingsConfigDict(env_prefix="GITHUB_")


def get_repo(token: str, repo_owner: str, repo_name: str) -> LapwingRepository:
    """Fetch the repository object for the given repository owner and name."""
    client = LapwingGitHubClient.instance(token=token)
    return client.repos.get(f"https://github.com/{repo_owner}/{repo_name}")


def get_content(repo: LapwingRepository, env_file_path: str, base_branch: str) -> tuple[str, str]:
    """Get the file content with the new release tag.

    Args:
        repo (LapwingRepository): The repository object.
        env_file_path (str): The path to the environment file.
        base_branch (str): The base branch to get content from.

    Returns:
        tuple[str, str]: File content and its SHA.
    """
    contents = repo.get_contents(env_file_path, ref=base_branch)
    if isinstance(contents, list):
        file_content_sha = contents[0].sha
        file_content = contents[0].decoded_content.decode("utf-8")
    else:
        file_content_sha = contents.sha
        file_content = contents.decoded_content.decode("utf-8")
    return file_content, file_content_sha


def update_content(file_content: str, release_tag: str) -> str:
    """Updates the file content with the new release tag.

    Args:
        file_content (str): The original file content.
        release_tag (str): The new release tag to be added.

    Returns:
        str: Updated file content.
    """
    updated_content: list[str] = []
    for line in file_content.split("\n"):
        if line.startswith("export IMAGE_VERSION="):
            updated_content.append(f"export IMAGE_VERSION={release_tag}")
        else:
            updated_content.append(line)
    return "\n".join(updated_content)


def upsert_branch(repo: LapwingRepository, new_branch: str, base_sha: str) -> None:
    """Creates a new branch or uses an existing one in the repository.

    Args:
        repo (LapwingRepository): The repository object.
        new_branch (str): The new branch to be created or used.
        base_sha (str): The base SHA to create the branch from.
    """
    try:
        repo.get_branch(new_branch)
        print(f"Branch '{new_branch}' already exists.")
    except GithubException:
        repo.create_git_ref(ref=f"refs/heads/{new_branch}", sha=base_sha)


def fetch_pr_details(inputs: DeployInputs) -> tuple[int, str]:
    """Fetch the PR details like PR number and SHA.

    Args:
        inputs (DeployInputs): The deployment inputs.

    Returns:
        tuple[int, str]: PR number and SHA.
    """
    repo = get_repo(inputs.token, inputs.repo_owner, inputs.repo_name)
    pulls = list(repo.get_pulls(head=f"{inputs.repo_owner}:{inputs.release_tag}", base="main", state="open"))

    if len(pulls) != 1:
        raise ValueError(f"Failed to fetch PR details: found {len(pulls)} open PRs with the head {inputs.repo_owner}:{inputs.release_tag}")

    pull = pulls[0]
    pr_number = pull.number
    pr_sha = pull.head.sha
    return pr_number, pr_sha


def get_check_suite_status(repo: LapwingRepository, commit_sha: str) -> Dict[str, Any]:
    """
    Fetches the check suite status for a specific commit in a GitHub repo.

    Args:
        repo (LapwingRepository): The repository object.
        commit_sha (str): The commit SHA to fetch check suites for.

    Returns:
        Dict[str, Any]: Check suite status.
    """
    commit = repo.get_commit(commit_sha)
    check_suites = list(commit.get_check_suites())
    return {"check_suites": check_suites}


def get_check_runs_status(repo: LapwingRepository, check_suite_id: int) -> Dict[str, Any]:
    """
    Retrieves the check run status for a given check suite in a GitHub repository.

    Args:
        repo (LapwingRepository): The repository object.
        check_suite_id (int): The check suite ID to fetch check runs for.

    Returns:
        Dict[str, Any]: Check run status.
    """
    check_suite = repo.get_check_suite(check_suite_id)
    check_runs = list(check_suite.get_check_runs())
    return {"check_runs": check_runs}


def approve_pull_request(bot_token: str, repo_owner: str, repo_name: str, pr_number: int) -> None:
    """
    Approves the given pull request using the bot token.

    Args:
        bot_token (str): The bot token to authenticate the approval.
        repo_owner (str): The repository owner.
        repo_name (str): The repository name.
        pr_number (int): The pull request number.
    """
    client = LapwingGitHubClient.instance(token=bot_token)
    repo = client.repos.get(f"https://github.com/{repo_owner}/{repo_name}")
    pull = repo.get_pull(pr_number)
    pull.create_review(event="APPROVE")
    print(f"PR #{pr_number} has been approved by the bot account.")


def is_pr_approved(repo: LapwingRepository, pr_number: int) -> bool:
    """
    Checks if the pull request has been approved.

    Args:
    repo (LapwingRepository): The repository object.
    pr_number (int): The pull request number to check.

    Returns:
    bool: True if the PR is approved, False otherwise.
    """
    pull = repo.get_pull(pr_number)
    reviews = pull.get_reviews()
    approved = any(review.state == "APPROVED" for review in reviews)
    return approved


def pr_merge(  # pylint: disable=too-many-arguments
    token: str,
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    commit_title: str = "Merging Passing PR",
    commit_message: str = "Merging PR automatically as all checks have passed",
    merge_method: str = "squash",
) -> None:
    """
    Forces merge for a pull request.

    Args:
        bot_token (str): The bot token to authenticate the merge.
        repo_owner (str): The repository owner.
        repo_name (str): The repository name.
        pr_number (int): The pull request number.
        commit_title (str): The commit title for the merge.
        commit_message (str): The commit message for the merge.
        merge_method (str): The merge method to use.
    """
    client = LapwingGitHubClient.instance(token=token)
    repo = client.repos.get(f"https://github.com/{repo_owner}/{repo_name}")
    pull = repo.get_pull(pr_number)
    try:
        result = pull.merge(commit_message=commit_message, commit_title=commit_title, merge_method=merge_method)
        if result.merged:
            print(f"PR #{pr_number} has been merged successfully.")
        else:
            print(f"Failed to merge PR #{pr_number}: {result.message}")
            raise RuntimeError(f"Failed to merge PR #{pr_number}: {result.message}")
    except GithubException as exc:
        print(f"Exception during merge: {exc}")
        raise


def verify_deployment(api_url: str, max_attempts: int = 10, wait_time: int = 30, timeout: int = 10) -> bool:
    """
    Verifies if the deployment is running by checking the API endpoint.

    Args:
        api_url (str): The API URL to verify.
        max_attempts (int): The maximum number of attempts to verify the deployment.
        wait_time (int): The wait time between each attempt.
        timeout (int): The timeout for each API request.

    Returns:
        bool: True if the deployment is verified successfully, False otherwise.
    """
    for attempt in range(max_attempts):
        try:
            response = requests.get(api_url, verify=False, timeout=timeout)
            if response.status_code == 200:
                print("Deployment verification successful. API is running.")
                return True
            print(f"Attempt {attempt + 1} failed: {response.status_code} {response.reason}")
        except requests.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")

        if attempt < max_attempts - 1:
            print(f"Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
        else:
            print("Maximum attempts reached. Deploy verification failed.")

    print("Deployment verification failed. The API is not running as expected.")
    return False


def initialize_inputs() -> DeployInputs:
    """Initialize and return deployment inputs.

    Returns:
        DeployInputs: The initialized deployment inputs.
    """
    return DeployInputs()


def prepare_environment(repo: LapwingRepository, base_branch: str, env_file_path: str) -> tuple[str, str, str]:
    """Prepare the working environment by fetching necessary data from the repository.

    Args:
        repo (LapwingRepository): The repository object.
        base_branch (str): The base branch to work with.
        env_file_path (str): The path to the environment file.

    Returns:
        tuple[str, str, str]: The base SHA, file content, and file content SHA.
    """
    base_branch_ref = repo.get_branch(base_branch)
    base_sha = base_branch_ref.commit.sha
    file_content, file_content_sha = get_content(repo, env_file_path, base_branch)
    return base_sha, file_content, file_content_sha


def create_pull_request(  # pylint: disable=too-many-arguments
    repo: LapwingRepository,
    release_tag: str,
    base_sha: str,
    env_file_path: str,
    commit_message: str,
    base_branch: str,
    file_content: str,
    file_content_sha: str,
    target_env: str,
) -> Dict[str, Any]:
    """Create a pull request with the updated content.

    Args:
        repo (LapwingRepository): The repository object.
        release_tag (str): The release tag.
        base_sha (str): The base SHA to create the branch from.
        env_file_path (str): The path to the environment file.
        commit_message (str): The commit message for the pull request.
        base_branch (str): The base branch for the pull request.
        file_content (str): The file content.
        file_content_sha (str): The file content SHA.

    Returns:
        Dict[str, Any]: The pull request details.
    """
    updated_content = update_content(file_content, release_tag)
    new_branch = release_tag
    upsert_branch(repo, new_branch, base_sha)
    repo.update_file(env_file_path, commit_message, updated_content, file_content_sha, branch=new_branch)

    pr_title = f"Update {target_env} image tag with {release_tag}"
    pr_body = f"### Automated Update {target_env} image tag in `{env_file_path}` with {release_tag}."

    pr = repo.create_pull(
        title=pr_title,
        body=pr_body,
        head=new_branch,
        base=base_branch,
    )
    return {"pr": pr, "pr_url": pr.html_url, "pr_number": pr.number}


def handle_pr_creation(inputs: DeployInputs, repo: LapwingRepository, base_branch: str, skip_merge: bool) -> Dict[str, Any]:
    """Handle the creation of the pull request, selecting the target file based on skip_functions.

    Args:
        inputs (DeployInputs): The deployment inputs.
        repo (LapwingRepository): The repository object.
        base_branch (str): The base branch for the pull request.
        skip_merge (bool): Flag indicating if approval/merge steps should be skipped.

    Returns:
        Dict[str, Any]: The pull request details.
    """
    if skip_merge:
        env_file_path = inputs.prod_env_file_path
        target_env = "PROD"
    else:
        env_file_path = inputs.pre_prod_env_file_path
        target_env = "PRE-PROD"

    if not env_file_path:
        raise ValueError(f"Environment file path not provided for {target_env} environment")
        
    logging.info("Targeting %s environment file: %s because --skip-merge=%s.", {target_env}, {env_file_path}, {skip_merge})

    commit_message = f"Update {target_env} ({env_file_path}) with image tag {inputs.release_tag}"

    base_sha, file_content, file_content_sha = prepare_environment(repo, base_branch, env_file_path)
    pr_details = create_pull_request(
        repo, inputs.release_tag, base_sha, env_file_path, commit_message, base_branch, file_content, file_content_sha, target_env
    )
    pr_details["target_env"] = target_env
    return pr_details


def process_check_run(check_run: Any, all_check_runs_complete: bool) -> tuple[str, bool]:
    """Processes a single check run, determines its state, and updates the all_check_runs_complete flag.

    Args:
        check_run (Any): The check run object.
        all_check_runs_complete (bool): Flag indicating if all check runs are complete.

    Returns:
        tuple[str, bool]: The state of the check run and the updated all_check_runs_complete flag.
    """
    logging.info("Processing check run: %s, Status: %s, Conclusion: %s", check_run.name, check_run.status, check_run.conclusion)
    if check_run.status == "completed":
        if check_run.conclusion in ["success", "skipped", "neutral"]:
            state = "success"
        elif check_run.conclusion in ["failure", "timed_out", "action_required", "stale", "cancelled"]:
            state = "failure"
        elif check_run.conclusion is None:
            state = "pending"
            logging.warning("Check run '%s' has status 'completed' but conclusion is None. Setting state to 'pending'.", check_run.name)
        else:
            state = "pending"
            logging.warning(
                "Check run '%s' has status 'completed' but conclusion is unexpected: '%s'. Setting state to 'pending'.",
                check_run.name,
                check_run.conclusion,
            )
    elif check_run.status in ["in_progress", "queued"]:
        state = "pending"
        all_check_runs_complete = False
    else:
        state = "pending"
        logging.warning("Check run '%s' has unexpected status: '%s'. Setting state to 'pending'.", check_run.name, check_run.status)
        all_check_runs_complete = False
    return state, all_check_runs_complete


def update_local_commit_status(  # pylint: disable=too-many-arguments
    local_repo: LapwingRepository, local_commit_sha: str, check_run: Any, state: str, pr_number: int, pr_url: str, release_tag: str
) -> None:
    """Updates the local commit status with the given check run details.

    Args:
        local_repo (LapwingRepository): The local repository object.
        local_commit_sha (str): The local commit SHA.
        check_run (Any): The check run object.
        state (str): The state to set for the commit status.
        pr_number (int): The pull request number.
        pr_url (str): The pull request URL.
    """
    context = f"{check_run.name}  / v{release_tag}"
    description = f"PR #{pr_number}"
    local_repo.get_commit(local_commit_sha).create_status(
        state=state,
        target_url=pr_url,
        description=description,
        context=context,
    )
    logging.info(
        "Updated local check run '%s' with status '%s' and conclusion '%s'.",
        context,
        state,
        check_run.conclusion,
    )


def sync_local_commit_with_remote_checks(inputs: DeployInputs, pr_url: str) -> None:  # pylint: disable=R0914
    """
    Update commit status based on the release tag's commit.

    Args:
        inputs (DeployInputs): The deployment inputs containing repository details.
        pr_url (str): The pull request URL.
    """
    try:
        local_repo = get_repo(inputs.token, inputs.local_repo_owner, inputs.local_repo_name)

        try:
            local_tag = local_repo.get_git_ref(f"tags/{inputs.release_tag}")
            local_commit_sha = local_tag.object.sha
            logging.info("Local Tag '%s' commit SHA: %s", inputs.release_tag, local_commit_sha)
        except GithubException:
            logging.warning("Tag '%s' not found in local repository. Cannot update status for this tag.", inputs.release_tag)
            return

        remote_repo = get_repo(inputs.token, inputs.repo_owner, inputs.repo_name)
        pr_number, remote_commit_sha = fetch_pr_details(inputs)
        logging.info("Remote PR Number: %s", pr_number)
        logging.info("Remote PR SHA: %s", remote_commit_sha)

        remote_check_suites_data = get_check_suite_status(remote_repo, remote_commit_sha)
        remote_check_suites = remote_check_suites_data.get("check_suites", [])

        if not remote_check_suites:
            logging.info("No check suites found in remote repository.")
            return

        all_check_runs_complete = False
        while not all_check_runs_complete:
            all_check_runs_complete = True
            for suite in remote_check_suites:
                remote_check_runs_data = get_check_runs_status(remote_repo, suite.id)
                remote_check_runs = remote_check_runs_data.get("check_runs", [])

                for check_run in remote_check_runs:
                    state, all_check_runs_complete = process_check_run(check_run, all_check_runs_complete)
                    if check_run.status == "completed":
                        update_local_commit_status(local_repo, local_commit_sha, check_run, state, pr_number, pr_url, inputs.release_tag)

            if not all_check_runs_complete:
                logging.info("Some check runs are not completed yet. Checking again in 30 seconds...")
                time.sleep(30)

    except GithubException as exc:
        logging.error("An error occurred while fetching tag or check suites: %s", exc)
        raise


def monitor_checks(repo: LapwingRepository, pr_sha: str) -> bool:
    """Monitor all check runs present for the PR."""
    observed_check_names = set()
    failed_checks: set[str] = set()

    check_suites_data = get_check_suite_status(repo, pr_sha)
    check_suites = check_suites_data.get("check_suites", [])
    for suite in check_suites:
        check_runs_data = get_check_runs_status(repo, suite.id)
        check_runs = check_runs_data.get("check_runs", [])
        for run in check_runs:
            observed_check_names.add(run.name)

    print(f"Observed check runs for this PR: {observed_check_names}")

    while True:
        completed = set()
        failed_checks.clear()
        check_suites_data = get_check_suite_status(repo, pr_sha)
        check_suites = check_suites_data.get("check_suites", [])
        for suite in check_suites:
            check_runs_data = get_check_runs_status(repo, suite.id)
            check_runs = check_runs_data.get("check_runs", [])
            for run in check_runs:
                if run.name not in observed_check_names:
                    continue
                if run.status != "completed":
                    continue
                completed.add(run.name)
                if run.conclusion == "failure":
                    failed_checks.add(run.name)
        if completed == observed_check_names:
            break
        print("Some check runs are not completed yet. Checking again in 60 seconds...")
        time.sleep(60)

    if failed_checks:
        print(f"Status: Failed (failed checks: {failed_checks})")
        return False

    print("Status: Success")
    return True


def main(skip_merge: bool = False) -> None:
    """The main function that runs the deployment process."""
    base_branch = "main"

    inputs = initialize_inputs()
    repo = get_repo(inputs.token, inputs.repo_owner, inputs.repo_name)

    try:
        pr_details = handle_pr_creation(inputs, repo, base_branch, skip_merge)
        target_env = pr_details.get("target_env", "UNKNOWN")

        pr_number, pr_sha = fetch_pr_details(inputs)
        pr_url = pr_details["pr_url"]

        # Print PR details immediately after creation
        print(f"Successfully created a pull request for {target_env}: {pr_url}")
        print(f"PR Number: {pr_number}")
        print(f"PR SHA: {pr_sha}")
        print(f"PR URL: {pr_url}")
        print(f"Target Environment: {target_env}")

        time.sleep(10)

        # Sync local commit status in background but don't wait for completion
        sync_local_commit_with_remote_checks(inputs, pr_url)
        
        # Monitor checks and show progress
        all_checks_passed = monitor_checks(repo, pr_sha)

        if skip_merge:
            print(f"Skipping approval, merge, and verification steps for {target_env} due to --skip-functions flag.")
        elif all_checks_passed:
            print(f"All checks passed for {target_env}. Proceeding with approval, merge, and verification.")
            try:
                approve_pull_request(inputs.bot_token, inputs.repo_owner, inputs.repo_name, pr_number)
                time.sleep(10)

                if is_pr_approved(repo, pr_number):
                    print("PR approved, proceeding with merge.")
                    pr_merge(inputs.token, inputs.repo_owner, inputs.repo_name, pr_number)
                    time.sleep(45)
                    api_url = "https://api.lapwing-pre.altera.com/schema"
                    if verify_deployment(api_url):
                        print("Deployment verification passed.")
                    else:
                        print("Deployment verification failed after merge.")
                        raise RuntimeError("Deployment verification failed after merge.")
                else:
                    print("PR has not been approved. Cannot proceed with the merge.")
                    raise RuntimeError("PR has not been approved.")

            except Exception as exc:
                print(f"An error occurred during the approval/merge/verify process: {exc}")
                raise
        else:
            print("Skipping approval, merge, and verification steps because checks failed.")
            raise RuntimeError("Deployment failed due to failed checks.")

        print("Script execution finished.")

    except Exception as exc:
        print(f"An error occurred during the main execution flow: {exc}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deployment script with optional function skipping.")
    parser.add_argument(
        "--skip-merge",
        action="store_true",
        help="Skip the approve_pull_request, is_pr_approved, pr_merge, verify_deployment functions.",
    )
    args = parser.parse_args()

    try:
        main(skip_merge=args.skip_merge)
    except Exception as exc:
        logging.error("An error occurred: %s", exc, exc_info=True)
        raise
