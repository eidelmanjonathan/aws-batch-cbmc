# Padstone CI Deployment

For the Padstone project we need to be able to run proofs as part of the CI process of several different projects.
We would like to have our way of deploying and running these CI systems be as flexible and robust as possible. 
Our CI Deployment infrastructure needs to do several different things effectively. 

1. Configuration management of tools: cbmc, CBMC-batch, lambdas for communicating with GitHub and running CBMC-batch
2. Configuration management of project build information: github repository and branch information
3. Reporting and failure management: alarms, emails, and tracing tools
4. Regression and replayability of proofs: we should be able to re-run specific github commits with specific versions of tools.

Because we have several different projects that we would like to run CI for, and these projects each have their own specific tooling needs (for example you might have a particular version of CBMC being used by a particular project), we need a way to manage these tools.
The current way that this is set up is to have one AWS account devoted to CI per project.  
We would like to be able to easily set up several accounts that use the same set of tools, or to be able set up one account to have the same set of tools and be deployed using the same Cloudformation templates as another account (for example promoting a beta account to prod). 


We also have to track and manage project specific information, (like project names, and which email addresses to send alerts to, etc..) 
These need to be separated from data that can be shared between accounts. The current way we achieve this separation is by having a shared “build tools” account, with an S3 bucket that contains all information about sets of tools and Cloudformation templates. Each of these sets is assigned a “Snapshot ID”.
So if we want to deploy a project account using those tools and those templates, we can simply deploy that Snapshot ID. 
Then any project specific parameters that need to be assigned to the project account and provided by the user at the time of deployment.
These are things like project name, and which email address we should send alerts to. 
These are provided in a JSON file at the time of deployment.

One of the issues we have now is that the code that handles configuration management is intermixed with the code that handles project build data. 
We would like to have a well-organized way of managing these AWS accounts, and want to be sure that we are able to control exactly what set of tools is running in each account. 
We also want to avoid accidentally leaking any project specific data into our shared S3 bucket. 

Another essential property our CI system needs to achieve is that we want to be able to easily rollback a project account to a previous state. 
This is useful in case we introduce a bug that breaks the CI and we need to return to a prior stable state where CI was working. 
It is also useful because sometimes we have a particular proof that failed at some point that is no longer failing anymore, and it is important to be able to try to reproduce the failure in the same environment, using the same tools as when it originally happened.

## Usage

### Managing a Shared Tools Account

Before setting up an account to run proofs in CI, we first need a shared tools account that will build our tool binaries and manage account snapshots. 

In order to manage a build tools account, you will need an AWS profile set up in your ~/.aws/config file pointing to the account. 
You will also need a JSON file with the particular parameters you would like to use in your account. 
This JSON looks like this:

    {
        "BatchCodeCommitBranchName": "snapshot",
        "BatchRepositoryBranchName": "master",
        "BatchRepositoryName": "aws-batch-cbmc",
        "BatchRepositoryOwner": "awslabs",
        "ViewerRepositoryBranchName": "cbmc-viewer"
        "ViewerRepositoryName": "cbmc",
        "ViewerRepositoryOwner": "markrtuttle"
    }
    
These parameters will decide the git repos and other properties we will use to set up the account.

#### First Time Deployment of Tools Account

If this is the first time we are ever setting up this shared tools account, need to deploy it from templates that are locally on our laptops. 
In general, we will deploy from snapshots that are stored in S3, but the very first time there is no S3 bucket so we must deploy from the local templates:

    cd PATH-TO-CBMC-BATCH/ci/snapshot
    tools_deploy --build-profile PROFILE --tools-parameters PATH_TO_PARAMETERS_FILE --bootstrap-from-local-templates
    
We need to be in the right directory since we are using the local template files.
Once this command succeeds, we should then immediately follow the ordinary workflow for deploying the shared tools account, so that we will have a snapshot ID and can rollback if we need to

Finally, we need to set the permissions on the ECR repositories that hold our containers. 
This is currently not automated and must be done manually. 
Proof accounts must be given the following permissions to access the CBMC ECR repository:

1. ecr:BatchCheckLayerAvailability
2. ecr:BatchGetImage
3. ecr:GetDownloadUrlForLayer
4. ecr:ListImages

#### Ordinary Deployment of Tools Account

    tools_deploy.py --build-profile PROFILE --tools-parameters PATH_TO_PARAMETERS_FILE --generate-snapshot

This will give a snapshot ID that looks something like 20200203-201525. We can then deploy the snapshot:

    tools_deploy.py --build-profile PROFILE --tools-parameters PATH_TO_PARAMETERS_FILE \
        --deploy-snapshot --snapshot-id SNAPSHOT_ID
        
We can also combine these two steps with the following command:

    tools_deploy.py --build-profile PROFILE --tools-parameters PATH_TO_PARAMETERS_FILE \
        --generate-snapshot --deploy-snapshot
        

        
### Managing a Proof Account

In order to deploy a proof account, we will need a project parameters file for the particular proof account we are trying to set up. 
This will look something like this:

    {
        "ProjectName": "MQTT-Beta2",
        "NotificationAddress": "notification@email.com",
        "SIMAddress": "notification@email.com",
        "GitHubRepository": "eidelmanjonathan/amazon-freertos",
        "GitHubBranchName": "master"
        
    }

 This gives the specific parameters we want for our proof account.
 
 #### Generating a New Snapshot
 
In order to guarantee similar behaviour between accounts, we generate snapshots of the templates used to build an account, along with the binaries of the particular tools (CBMC, etc..) being used in the account. 
To generate a new snapshot, run the following command:
 
    padstone_deploy.py --proof-profile PROOF_PROFILE --build-profile BUILD_PROFILE \
        --project-parameters PATH_TO_PARAMETERS_FILE --generate-snapshot
 
This will create a new snapshot with the most recent templates and the most recently build tools binaries, and assign it an ID that looks like: 20200203-201525. 
 
Sometimes we don't want to use the most recent binaries and we would like to specify a specific cbmc package in the shared tools account. 
To do this, we create a package overrides json file which looks like this:
 
     {
        "cbmc": "cbmc-20200128-142813-dbac9633.tar.gz"
     }

The keys we can supply are cbmc, batch, viewer and lambda. 
The packages are packages in the shared tools S3 bucket packages directory.
In the shared tools S3 bucket, there is a directory called "packages" that has subdirectories for each tools.
That folder contains tarballs with names that look similar to the above.
Any of those tarballs can be chosen here.

If we want to generate a new snapshot with package overrides, we use the following command:

    padstone_deploy.py --proof-profile PROOF_PROFILE --build-profile BUILD_PROFILE \
        --project-parameters PATH_TO_PARAMETERS_FILE --generate-snapshot --package-overrides PATH_TO_OVERRIDES_FILE


### Deploying a snapshot

To deploy a snapshot we use the following command:

    padstone_deploy.py --proof-profile PROOF_PROFILE --build-profile BUILD_PROFILE \
        --project-parameters PATH_TO_PARAMETERS_FILE --deploy-snapshot --snapshot-id ID

If we would like to promote a snapshot from one account to another (to guarantee that those accounts should have similar behaviour - for example promoting a snapshot from beta to prod), we use the following command:

    padstone_deploy.py --proof-profile PROOF_PROFILE --build-profile BUILD_PROFILE 
        --source-proof-profile SOURCE_PROFILE --project-parameters PATH_TO_PARAMETERS_FILE \
        --deploy-snapshot
        
        
        
## Architecture of Snapshot and CI Account Management System

Here is the proposed architecture, going from the lowest level modules up to the higher level modules:

### Layer 1: AWS Service Controllers

The purpose of these modules is to handle interactions with individual AWS services.

#### CloudformationStacks

This class handles everything to do with deploying, waiting for, checking the status of and retrieving output values from stacks in Cloudformation.

#### BucketPolicyManager

This package handles parsing and changing S3 bucket policies to change permissions for different accounts. 
In our case, so far we only use it to give read access to the shared bucket to project/proof accounts.

#### PipelineManager

Sometimes if we have pushed new code and want to make sure we are using that code, we want to trigger a particular pipeline. 
Also we may sometimes want to wait for several pipelines to finish running before we move on to the next step of our process. 
This module provides functionality for triggering and waiting for pipelines.

#### SnapshotManager

The purpose of this module is to take a snapshot of all of the templates and packages being run in an account and then save them in S3 so they could be redeployed later if we wanted to. 

### Layer 2: Orchestrating AWS services within an account

#### AwsAccount

The purpose of the AWS account class is to give a give a generic interface for deploying several stacks concurrently, and then waiting for them to be in a stable state. 
It also allows us to specify that we want to wait for pipelines to complete once a particular stack has been updated, and allows us to specify what input parameters each stack takes, and a ParameterManager that will determine how those parameters get assigned (since they often come from multiple sources). 
The most important method this exposes is:

    def deploy_stacks(self, stacks_to_deploy, s3_template_source=None, overrides=None):

Where stacks_to_deploy is the specifications for which stacks we want to deploy, which templates they need (these templates can either come from S3 in the shared account, S3 in the proof account, or locally depending on the s3_template_source value.
The default behaviour is to look for the templates locally in the current folder.

The specification takes the form of a dictionary that looks like this:

    BUILD_TOOLS_CLOUDFORMATION_DATA = {
        "build-batch": {
            TEMPLATE_NAME_KEY: "build-batch.yaml",
            PARAMETER_KEYS_KEY: ['BatchRepositoryBranchName',
                                 'BatchRepositoryName',
                                 'BatchRepositoryOwner',
                                 'GitHubToken',
                                 'S3BucketName'],
            PIPELINES_KEY: ["Build-Batch-Pipeline"]
        },
        "build-viewer": {
            TEMPLATE_NAME_KEY: "build-viewer.yaml",
            PARAMETER_KEYS_KEY: ['GitHubToken', 
                                 'S3BucketName', 
                                 'ViewerRepositoryBranchName', 
                                 'ViewerRepositoryName', 
                                 'ViewerRepositoryOwner'],
            PIPELINES_KEY: ["Build-Viewer-Pipeline"]
        }
    }

Which says that we would like to concurrently start deploying build-batch and build-viewer templates, and it gives the parameters that each of these templates need.
These parameters are simply the input parameters of the Cloudformation template. 
The parameters will be supplied using the ParametersManager. 
It also specifies that once we deploy these templates and the stacks are stable, we would like to wait for the "Build-Batch-Pipeline" and the "Build-Viewer-Pipeline" to complete.

#### ParameterManager

When there is a parameter to be filled in a Cloudformation template, there are often several different places we want to look for the value. 
The parameter manager handles filling in values for Cloudformation parameters, making sure there are no inconsistencies and deciding on which values should get priority. 
It also handles any logic to do with preprocessing the parameters. 
An example of this is where we need to use the BucketPolicyManager to figure out all of the current accounts that our policy allows, so that we can update the stack with one more account.

### Layer 3: Orchestrating multiple AWS accounts/profiles

When deploying proof accounts, we need access to the shared tool account to do things like download templates and update the bucket policy. 
Also, we may also later want to have the flexibility of running things in different regions.

Because of this, I propose we have an AccountOrchestrator which will keep an AwsAccount object for any profile that we deal with. 
This will handle all of the logic of passing the appropriate stacks_to_deploy specifications (these will be kept as constant dictionaries in a centralized location so they can be easily adjusted when necessary), as well as any data that must be passed from one account to another. 

The advantage of having this layer is that we can see very clearly and easily when we are passing data from one account to another, whereas before it was somewhat hidden in the code and hard to find. 
This minimizes the chances that we will accidentally pass project specific data to a shared account or some other careless error. 
It makes our decisions very explicit and visible, while also giving flexibility in case we realize we need to pass more or less data in the future.
