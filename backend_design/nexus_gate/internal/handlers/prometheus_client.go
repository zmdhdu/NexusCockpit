// Copyright (c) 2026 zhangmengdi (NexusCockpit)
// Licensed under the MIT License. See LICENSE in the project root for details.
// Source: https://github.com/zmdhdu/NexusCockpit

// Package handlers — Prometheus HTTP API 查询客户端
//
// 通过 HTTP GET /api/v1/query 查询 Prometheus 实时指标，
// 替代原来 dataplatform 并发/QPS 硬编码占位 0 的逻辑。
package handlers

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"time"
)

// promQueryResult 匹配 Prometheus /api/v1/query 响应结构
type promQueryResult struct {
	Status string `json:"status"`
	Data   struct {
		ResultType string `json:"resultType"`
		Result     []struct {
			Metric map[string]string `json:"metric"`
			Value  [2]interface{}    `json:"value"` // [timestamp, "value_string"]
		} `json:"result"`
	} `json:"data"`
	Error string `json:"error,omitempty"`
}

// queryPrometheus 向 Prometheus 发送一条 PromQL 查询，返回标量结果。
//
// 如果查询失败、返回多个序列或值为 NaN，则返回 fallback。
//
// 参数:
//   - prometheusURL: Prometheus 基地址（如 "http://127.0.0.1:9200"）
//   - query: PromQL 查询表达式
//   - fallback: 查询失败时的降级返回值
func queryPrometheus(prometheusURL, query string, fallback float64) float64 {
	client := &http.Client{Timeout: 3 * time.Second}

	apiURL := fmt.Sprintf("%s/api/v1/query?query=%s",
		prometheusURL, url.QueryEscape(query))

	resp, err := client.Get(apiURL)
	if err != nil {
		return fallback
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fallback
	}

	var result promQueryResult
	if err := json.Unmarshal(body, &result); err != nil {
		return fallback
	}
	if result.Status != "success" || len(result.Data.Result) == 0 {
		return fallback
	}

	// 取第一个序列的值
	valStr, ok := result.Data.Result[0].Value[1].(string)
	if !ok {
		return fallback
	}

	val, err := strconv.ParseFloat(valStr, 64)
	if err != nil {
		return fallback
	}

	return val
}

// queryPrometheusPerCockpit 查询每个座舱的指标，返回 map[cockpitID]value。
//
// 用于 per_cockpit 并发/QPS 分项展示。
func queryPrometheusPerCockpit(prometheusURL, queryTemplate string, cockpitCount int) []map[string]interface{} {
	result := []map[string]interface{}{}
	for i := 1; i <= cockpitCount; i++ {
		cockpitID := fmt.Sprintf("cockpit-0%d", i)
		// 将 {cockpit_id} 占位符替换为实际座舱 ID
		query := fmt.Sprintf(queryTemplate, cockpitID)
		val := queryPrometheus(prometheusURL, query, 0)
		result = append(result, map[string]interface{}{
			"cockpit_id":          cockpitID,
			"current_concurrency": int64(val),
			"qps":                int64(queryPrometheus(prometheusURL,
				fmt.Sprintf("sum(rate(nexus_requests_total{cockpit_id=\"%s\"}[1m]))", cockpitID), 0)),
		})
	}
	return result
}
