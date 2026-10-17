targetScope = 'resourceGroup'

@description('Azure region for all resources.')
param location string = resourceGroup().location
@description('Globally unique suffix for names.')
param namePrefix string = 'cqrs-faceted-search'
@description('Container image published by the deployment workflow.')
param apiImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
@description('GitHub repository in owner/name form for OIDC.')
param githubRepository string = 'example/cqrs-faceted-search'
@description('Object id of the Entra administrator for PostgreSQL.')
param entraAdminObjectId string = '00000000-0000-0000-0000-000000000000'

var suffix = uniqueString(resourceGroup().id)
var searchName = '${namePrefix}-search-${suffix}'
var postgresName = '${namePrefix}-pg-${suffix}'
var eventTopicName = '${namePrefix}-events-${suffix}'
var logName = '${namePrefix}-logs-${suffix}'
var envName = '${namePrefix}-env-${suffix}'
var apiName = '${namePrefix}-api-${suffix}'
var uiName = '${namePrefix}-ui-${suffix}'
var identityName = '${namePrefix}-identity-${suffix}'

resource logs 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logName
  location: location
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: searchName
  location: location
  sku: { name: 'basic' }
  properties: { hostingMode: 'default', replicaCount: 1, partitionCount: 1, publicNetworkAccess: 'enabled' }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: postgresName
  location: location
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: entraAdminObjectId
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    authConfig: { activeDirectoryAuth: 'Enabled', passwordAuth: 'Disabled' }
  }
}

resource pgDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-06-01-preview' = {
  parent: postgres
  name: 'catalog'
}

resource events 'Microsoft.EventGrid/topics@2023-12-15-preview' = {
  name: eventTopicName
  location: location
  properties: { inputSchema: 'EventGridSchema', publicNetworkAccess: 'Enabled' }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

resource federated 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: identity
  name: 'github-actions'
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    subject: 'repo:${githubRepository}:ref:refs/heads/main'
    audiences: [ 'api://AzureADTokenExchange' ]
  }
}

resource searchRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, identity.id, 'Search Index Data Contributor')
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8ebe5a00-799e-43f5-93ac-243d3dcead7b')
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource env 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: envName
  location: location
  properties: { appLogsConfiguration: { destination: 'log-analytics', logAnalyticsConfiguration: { customerId: logs.properties.customerId, sharedKey: logs.listKeys().primarySharedKey } } }
}

resource api 'Microsoft.App/containerApps@2023-05-01' = {
  name: apiName
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  properties: {
    managedEnvironmentId: env.id
    configuration: { ingress: { external: true, targetPort: 8000, transport: 'http' }, activeRevisionsMode: 'Single' }
    template: {
      containers: [{
        name: 'api'
        image: apiImage
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: [{ name: 'PORT', value: '8000' }]
      }]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

resource ui 'Microsoft.Web/staticSites@2022-09-01' = {
  name: uiName
  location: location
  sku: { name: 'Free' }
  properties: { allowConfigFileUpdates: true }
}

output searchEndpoint string = 'https://${search.name}.search.windows.net'
output postgresServer string = postgres.properties.fullyQualifiedDomainName
output apiUrl string = api.properties.configuration.ingress.fqdn
output staticSiteName string = ui.name
