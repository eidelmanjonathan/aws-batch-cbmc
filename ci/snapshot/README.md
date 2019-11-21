# Overview

Deploying continuous integration into an AWS account requires creating an
AWS account and deploying the continuous integration infrastructure.

## Create an AWS account

Go to https://isengard.amazon.com -> Create/Register Account ->
Create a new AWS account -> Create and Register

Accept all the defaults, but:

* account email: aws-arg-padstone+projectname@amazon.com where projectname
  is a string like mqtt or mqtt-beta that does not contain +
* posix group owner: aws-arg-padstone
* account name: aws-arg-padstone+projectname where projectname is the
  same as above
* description: any reasonable description like
  "Padstone CI for MQTT (beta account)"
* account type: Service Account with CTI
  aws -> it security - automated reasoning -> padstone
* data classification: not used for production

Add role Admin

* Add permission: posix group aws-arg-padstone
* Attach policy: AdministratorAccess

Add role ReadOnly

* Add permission: posix group aws-arg-padstone
* Attach policy: ReadOnlyAccess

Move into padstone group

* On the account page (click on 'view/edit' in the left menu),
set Group -> Change -> Padstone

Add to .aws/config a profile

        [profile PROFILE]
        account = AWS_ACCOUNT_ID
        region = us-west-2
        role = Admin

where `AWS_ACCOUNT_ID` is the account id.  Note that the region is
us-west-2.  When you log into the AWS console, be sure the region is
set to us-west-2.

## Deploy the continuous integration infrastructure

The continuous integration infrastructure is divided into two accounts. One account maintains builds of all the tools 
that are used for the Padstone project like CBMC, CBMC Batch etc... The second account actually performs the proofs. 
Many different Proof accounts (Beta, Prod, Development) can share the same Tool account.

* Choose email addresses (For each account, both Tool Build and Proof accounts):

    * NOTIFICATION_ADDRESS: Error events will send email to this address.  Use

      ```
      aws-arg-padstone@amazon.com
      ```

      for a production account, but feel free to use $USER@amazon.com for a
      testing account.

    * SIM_ADDRESS: Error events will send email to this address to generate a
      SIM ticket.  Use

      ```
      issues+create+91b477f7-c17e-43b9-b5fe-7e666b0bd1c6@email.amazon.com
      ```

      for a production account, but feel free to use $USER@amazon.com for a testing account.

* Verify email addresses with SES:

  ```
  aws --profile $PROFILE ses verify-email-identity --email-address NOTIFICATION_ADDRESS
  aws --profile $PROFILE ses verify-email-identity --email-address SIM_ADDRESS
  ```

* Obtain a GitHub personal access token at

  ```
  https://github.com/settings/tokens/new
  ```

  with permissions "repo" and "admin:repo\_hook". Use this as `ACCESS_TOKEN` below.

* Generate a random string. Use this as SECRET below.

* Setup secrets in Secrets Manager as follows.
  (Note: If the account you
  are building is a companion to another account ---
  maybe beta and prod accounts for the same projects ---
  you might want to consider using the same
  secrets in both accounts to facilitate promotion from beta to prod, etc.
  You can list secrets with ```aws --profile PROFILE secretsmanager
  get-secret-value --secret-id SECRET``` where SECRET is one of
  GitHubCommitStatusPAT or GitHubSecret and PROFILE is the other account.)

  ```
  aws --profile $PROFILE secretsmanager create-secret --name GitHubCommitStatusPAT --secret-string '[{"GitHubPAT":"ACCESS_TOKEN"}]'
  aws --profile $PROFILE secretsmanager create-secret --name GitHubSecret --secret-string '[{"Secret":"SECRET"}]'
  ```

* Create a preliminary configuration file snapshot.json like

  ```
  {
    "parameters": {
      "ProjectName": "MQTT-Beta",
      "NotificationAddress": "NOTIFICATION_ADDRESS",
      "SIMAddress": "SIM_ADDRESS",
      "BatchCodeCommitBranchName": "snapshot",
      "GitHubRepository": "aws/amazon-freertos"

    }
  }
  ```

  You can specify any parameter to the stacks here.  In particular, any parameter to
  build-globals.yaml and github.yaml like GitHubBranchName.  At the moment, the first three
  are required, and "BatchCodeCommitBranchName" must be set to "snapshot".
  ProjectName cannot contain a space or other "illegal" characters.
  

* If you are setting up both a completely new shared tool building account and a proof account, run the following command:

        snapshot-update --profile $PROOF-PROFILE --build-profile $BUILD-PROFILE --init-build-account --init-proof-account

* If you are using an existing tool building account, and are setting up a brand new proof account, run the following command:
        
        snapshot-update --profile $PROOF-PROFILE --build-profile $BUILD-PROFILE --init-proof-account
        
* If you would like to propose and create a new, updated snapshot and then use that snapshot in the proof account, run the following command:

        snapshot-update --profile $PROOF-PROFILE --build-profile $BUILD-PROFILE

* If you are promoting an existing proof account snapshot to a new proof account, using the same shared tools account, use the following command:

		snapshot-update --profile $PROOF-PROFILE --build-profile $BUILD-PROFILE --promote-from $SOURCE-PROFILE


* If you would like the account to post results to github, add the flag
		--is-prod

This will add read access for the proof account to the bucket policy of the shared tool account


The intention is that we would first run snapshot-update with --init-build-account and --init-proof-account flags, which would build all the globals in the shared tools account, create a new snapshot in the proof account, and deploy that snapshot in the proof account.

Next, if we needed to initialize a new proof account to share the build account we would use the --init-proof-account flag which would create a new snapshot in the proof account and deploy it in the proof account.

If we want to propose and deploy and updated snapshot for an existing proof account (which already has its S3 bucket deployed), we can run snapshot-update without any extra flags.

Finally, to promote a snapshot from one account to another, we use --promote-from which takes the source account as an argument. This builds a new snapshot in the target account that has the same packages as the source account

TODO: For now we must manually give permissions for ECR images to be publicly readable from the shared build account. In the future we should automate this,
and we should give finer grained permissions in case we eventually have images that are not open source

* Configure the web hook on GitHub. The required ID is the id listed by

        aws --profile $PROFILE apigateway get-rest-apis

        {
            "items": [
                {
                    "id": "v0sfq881hk",
                    "name": "LambdaAPI",
                    "description": "API provided to GitHub",
                    "createdDate": 1551369544,
                    "apiKeySource": "HEADER",
                    "endpointConfiguration": {
                        "types": [
                            "EDGE"
                        ]
                    }
                }
            ]
        }

  With this ID, configure the web hook

        https://ID.execute-api.us-west-2.amazonaws.com/verify

  as URL, application/json as the content type, and SECRET as secret. Select
  "Pushes" and "Pull requests" as the events triggering this webhook.

Note: It is normal to get a canary alarm minutes after this step completes.  The alarm
is warning you that there have been no runs of continuous integration (not even a canary)
in the last 24 hours, which is true and nothing to worry about today.

Isengard issues
---------------

Periodically my isengard credentials get messed up.  To get python3 scripts
to run again, I have to run

```
pip3 install --upgrade git+ssh://git.amazon.com/pkg/BenderLibIsengard
CERT_FILE="$("python3" -c 'import botocore; print(botocore.__path__[0])')/cacert.pem"
cp -v "$CERT_FILE" "$CERT_FILE.bak"
( security find-certificate -a -p ls "/System/Library/Keychains/SystemRootCertificates.keychain"; security find-certificate -a -p ls "/Library/Keychains/System.keychain"; ) > "$CERT_FILE"
```

Be sure your are running awscli and python3 installed by brew.  If the
above fails, try the same script but with

```
CERT_FILE="$("python3" -c 'import certifi; print(certifi.__path__[0])')/cacert.pem"
```

This information comes from the [AmazonAwsCli/Cookbook](https://w.amazon.com/index.php/AmazonAwsCli/Cookbook#IsengardPlugin).

Complaints about missing amazon_botocore should be solved with

```
pip install http://padb-public.s3-website-us-west-2.amazonaws.com/g34j57h3l19TIBMm97acZ5r5oUBUC9Wj/botocore_amazon-1.5.3.tar.gz
```

This information comes from [BotoCoreAmazon](https://w.amazon.com/index.php/BotoCoreAmazon).

Testing continuous integration
------------------------------

You can always start a run of continuous integration on the current state
of your repository by starting up a canary.

Use Isengard to federate into the account, go to Lambda, and go to the
lambda function beginning with the string "canary-".  Click on Test,
and the canary will grab the current commit of the repository and run
CBMC Batch on that commit.  If this is the first time you are testing
the canary, you will have to configure a test first: just click on "configure
test events" to see the HelloWorld test event, fill in the event name with "HelloWorld",
and click on create.

Replacing the production proof account with another account
-----------------------------------------------------------

This section describes how to replace the production account for an
existing proof project with a different account.

The AWS account that gathers our metrics and produces our metrics email
is [aws-arg-formal+ci@amazon.com](https://isengard.amazon.com/federate?account=323767359693&role=Admin) (323767359693).

The GitFarm repository that implements the metrics and metrics email is
[ARGContinuousIntegration](https://code.amazon.com/packages/ARGContinuousIntegration).

In that repository, there is one template that gives
the metrics account permission to scrap your logs for metrics:

* [scraping-role.yaml](https://code.amazon.com/packages/ARGContinuousIntegration/blobs/mainline/--/templates/scraping-role.yaml)

In that repository, there are three templates that explicitly
reference your account:

* [aws-arg-formal-ci.yaml](https://code.amazon.com/packages/ARGContinuousIntegration/blobs/mainline/--/templates/aws-arg-formal-ci.yaml)

* [metrics-email.yaml](https://code.amazon.com/packages/ARGContinuousIntegration/blobs/mainline/--/templates/metrics-email.yaml)

* [naws-projects.yaml](https://code.amazon.com/packages/ARGContinuousIntegration/blobs/mainline/--/templates/naws-projects.yaml)

The steps are

* Clone the respository:

  ```
  git clone ssh://git.amazon.com/pkg/ARGContinuousIntegration integration
  ```

* Add give the metrics account permission to scan your logs

  ```
  aws --profile $PROFILE cloudformation create-stack --stack-name metrics-scraping --template-body file://scraping-role.yaml --capabilities CAPABILITY_NAMED_IAM
  ```

* Verify the standard email addresses from your account:

  ```
  aws --profile $PROFILE ses verify-email-identity --email-address aws-arg-padstone@amazon.com
  aws --profile $PROFILE ses verify-email-identity --email-address issues+create+91b477f7-c17e-43b9-b5fe-7e666b0bd1c6@email.amazon.com
  ```

* Find the correct project name for your account given in [naws-projects.yaml](https://code.amazon.com/packages/ARGContinuousIntegration/blobs/mainline/--/templates/naws-projects.yaml)

* Redeploy the snapshot stacks in your account as described in the snapshot [README](https://code.amazon.com/packages/CBMC-batch/blobs/snapshot/--/lambda-github2/README.md), changing the project name, notification email address, and sim email address to match the ones used in the prior two steps.

* Edit [naws-projects.yaml](https://code.amazon.com/packages/ARGContinuousIntegration/blobs/mainline/--/templates/naws-projects.yaml) to change the account number there to your account number.  For example, change the account number 633910128321 in the line

  ```
  'arn:aws:iam::633910128321:role/t3-metrics-scraping-role': 'FreeRTOS',
  ```

* Commit the change and push the commit back to the repository:

  ```
  git add naws-projects.yaml
  git commit
  git push
  ```

* Create and publish a code review to let the CI team know about the change:

  ```
  cr --parent HEAD^ --reviewers team:proof-automation
  ```
