query "aws/costs" verb=POST {
  api_group = "app"
  auth = "usuarios"

  input {
    text start filters=trim
    text end filters=trim
  }

  stack {
    api.lambda {
      code = """
          const { default: aws4 } = await import("npm:aws4@1.13.2");
        
          // 1. Credenciais armazenadas no Xano
          const accessKeyId = $env.AWS_ACCESS_KEY_ID;
          const secretAccessKey = $env.AWS_SECRET_ACCESS_KEY;
        
          if (!accessKeyId || !secretAccessKey) {
            return {
              success: false,
              message: "Credenciais AWS não configuradas."
            };
          }
        
          // 2. Período recebido pelo endpoint
          const start = $input.start;
          const end = $input.end;
        
          function isValidDate(value) {
            if (typeof value !== "string") {
              return false;
            }
        
            if (value.length !== 10) {
              return false;
            }
        
            const date = new Date(value + "T00:00:00Z");
        
            return !Number.isNaN(date.getTime()) &&
              date.toISOString().slice(0, 10) === value;
          }
        
          if (!isValidDate(start) || !isValidDate(end) || start >= end) {
            return {
              success: false,
              status: 400,
              message: "Período inválido. Use YYYY-MM-DD e end posterior a start."
            };
          }
        
          // 3. Corpo da consulta ao Cost Explorer
          const host = "ce.us-east-1.amazonaws.com";
        
          const payload = {
            TimePeriod: {
              Start: start,
              End: end
            },
            Granularity: "MONTHLY",
            Metrics: ["UnblendedCost"],
            GroupBy: [
              {
                Type: "DIMENSION",
                Key: "SERVICE"
              }
            ]
          };
        
          const body = JSON.stringify(payload);
        
          // 4. Assinatura AWS Signature Version 4
          const credentials = {
            accessKeyId: accessKeyId,
            secretAccessKey: secretAccessKey
          };
        
          const signed = aws4.sign(
            {
              host: host,
              path: "/",
              method: "POST",
              service: "ce",
              region: "us-east-1",
              headers: {
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": "AWSInsightsIndexService.GetCostAndUsage"
              },
              body: body,
              extraHeadersToIgnore: {
                "content-length": true
              }
            },
            credentials
          );
        
          // O cliente HTTP calcula o Content-Length automaticamente.
          const headers = new Headers(signed.headers);
          headers.delete("content-length");
        
          // 5. Enviar a requisição para a AWS
          const response = await fetch("https://" + host + "/", {
            method: "POST",
            headers: headers,
            body: signed.body
          });
        
          const text = await response.text();
        
          let data;
        
          try {
            data = JSON.parse(text);
          } catch {
            data = { message: text };
          }
        
          // 6. Retornar o resultado ao Xano
          if (!response.ok) {
            return {
              success: false,
              status: response.status,
              error: data.__type || data.code || "AWS_REQUEST_FAILED",
              message: data.message || data.Message || "Erro na consulta AWS."
            };
          }
        
          return {
            success: true,
            status: response.status,
            data: data
          };
        """
      timeout = 30
    } as $aws_cost_result
  }

  response = $aws_cost_result
  guid = "zH7I8yty_9bE3fXJBScRhe4QQgM"
}