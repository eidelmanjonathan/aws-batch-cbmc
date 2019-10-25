Github Explorer Tool
=======

The purpose of this tool is to make it easier to debug 
and diagnose and debug proof failures. Currently the tool only debugs problems
that occured in the default branch of a project.

## Setup

In order to run the github explorer, we will need to have a local, up to date
clone of the particular github repository we are interested in. This copy should 
have the proofs ready to run. In the case of the FreeRTOS project, for example, 
we should already have run prepare.py so that the Makefiles are available for all proofs.

We should then create a params.json file, which gives all of the parameters that
the tool will use to interact with Github.

```
{
  "git-authentication": "AUTHENTICATION_STRING",
  "git-repo": "amazon-freertos",
  "git-owner": "aws",
  "local-repo-folder": "/PATH_TO/amazon-freertos/",
  "proofs-root-folder": "/tools/cbmc/proofs",
  "makefile": "/PATH_TO/amazon-freertos/tools/cbmc/proofs/Makefile.common",
  "makefile-dependency-text": "gcc -M ${INC} ${ENTRY}_harness.c"
}
```

Here, the local-repo-folder is the local path to the up to date clone of your repo.
The proofs-root-folder is the relative path in the repo to the root directory of the proofs.
The makefile parameter points to where the common Makefile for all the proofs is. 
And the makefile-depdency-text is the gcc command that should be used to get all of the dependencies
of a particular proof harness. This command varies very slightly between the projects.

## Usage

We would like to figure out where a particular proof failure was introduced to the current branch.
In order to do this we run the following command:

```
python3 github_tool.py --utc 2019-08-31T00:00:00 --get-broken-commits --interval-hours 24
```

This will give us a list of all pushes to the current branch, or merges of pull requests that failed proofs
within 24 hours of the utc time given, as well as the proofs that failed.

Then, once we have found the failed commit that we are interested in diagnosing, we can run

```
python3 github_tool.py --find-point-of-failure --commit-sha ad8ff9c56bb216bb3df8942d8c0ff2835f03cf09
```

This will find the most recent push or merge to the current branch where the proofs began failing.
Once we find this, we will compute the diff of that commit with the commit immediately before it when 
proofs were still succeeding. We will then spit out a JSON summary of the diffs for each file that is a
dependency of a proof harness that failed. We can also use the ``` ---pretty-print ``` option to print this
in a more readable format.

Finally, we can run 

```
python3 github_tool.py --find-fix --commit-sha ad8ff9c56bb216bb3df8942d8c0ff2835f03cf09
```

This will find both the point of failure, as well as where the proofs started working again, and will give the diff in 
proof Makefile and harness file of these two commits