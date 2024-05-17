/* Test Golang. */

package lens3

import (
	"bufio"
	"bytes"
	"context"
	//"encoding/json"
	"fmt"
	"log"
	"time"
	//"reflect"
	"io"
	"os"
	"os/exec"
	"os/signal"
	"strings"
	"syscall"
	"testing"
)

func Test_misc(t *testing.T) {
	// check_signal_handling()
	//test_start_process_with_timeout()
	//test_collect_process_output()
	//test_pipe_timeout()
	//test_get_lines()
	start_service_for_test()
	// check_type_switch_on_nil()
	// test_minimal_environ()
}

func test_minimal_environ() {
	// runtime.GOMAXPROCS(runtime.NumCPU())

	fmt.Println("test_minimal_environ")
	fmt.Println("minimal_environ()=", minimal_environ())
}

func check_type_switch_on_nil() {
	fmt.Println("check_type_switch_on_nil")
	var x error
	x = nil
	switch e := x.(type) {
	case *exec.ExitError:
		fmt.Print("e=", e)
	case nil:
		fmt.Print("e=", e)
	}
}

func check_signal_handling() {
	fmt.Println("check_signal_handling")
	fmt.Println("Catch INT/TERM; Stop by QUIT")

	var sig = make(chan bool)
	var loop = make(chan error)

	go signal_handler(sig)

	var int_or_term bool
	for {
		go func() {
			time.Sleep(3000 * time.Millisecond)
			loop <- nil
		}()

		select {
		case int_or_term = <-sig:
			fmt.Println("signal int_or_term=", int_or_term)
		case <-loop:
			fmt.Println("timer")
		}
	}
	fmt.Println("done unexpectedly")
}

func signal_handler(chq chan bool) {
	fmt.Println("signal_handler start")

	var ch1 = make(chan os.Signal, 1)
	signal.Notify(ch1, syscall.SIGINT, syscall.SIGTERM, syscall.SIGHUP)

	//var quit bool
	for signal := range ch1 {
		switch signal {
		case syscall.SIGINT:
			fmt.Println("SIGINT")
			chq <- true
		case syscall.SIGTERM:
			fmt.Println("SIGTERM")
			chq <- false
		case syscall.SIGHUP:
			fmt.Println("SIGHUP")
			os.Exit(0)
		}
	}
}

func test_start_process_with_timeout() {
	fmt.Println("test_start_process_with_timeout")

	var server_start_timeout = 1000 * time.Millisecond
	var ctx, cancel = context.WithTimeout(context.Background(),
		server_start_timeout)
	defer cancel()
	var cmd = exec.CommandContext(ctx, "sleep", "5")
	var err = cmd.Run()
	if err != nil {
		fmt.Println("cmd.Run() errs")
	}
	select {
	case <-ctx.Done():
		fmt.Println("ctx.Done()")
		fmt.Println(ctx.Err())
	}
}

func test_collect_process_output() {
	fmt.Println("test_collect_process_output")

	/* cmd.CombinedOutput should be called before Run. */
	/* cmd.CombinedOutput implies Run. */

	var ctx = context.Background()
	var cmd = exec.CommandContext(ctx, "head", "-2", "./LICENSE")

	var outs, errs bytes.Buffer
	cmd.Stdout = &outs
	cmd.Stderr = &errs

	//var outs, err2 = cmd.CombinedOutput()
	//if err2 != nil {
	//	fmt.Println("cmd.CombinedOutput() errs")
	//	panic(err2)
	//}
	//fmt.Println("combined", string(outs))

	var err1 = cmd.Run()
	if err1 != nil {
		fmt.Println("cmd.Run() errs", err1)
	}
	fmt.Println("outs=", outs.String())
	fmt.Println("errs=", errs.String())
}

func test_pipe_timeout() {
	fmt.Println("test_pipe_timeout")

	var ctx = context.Background()
	var cmd = exec.CommandContext(ctx, "head", "-2", "./LICENSE")

	o1, err1 := cmd.StdoutPipe()
	if err1 != nil {
		panic(err1)
	}
	//os.SetReadDeadline(time.Now().Add(10 * time.Second))
	e2, err2 := cmd.StderrPipe()
	if err2 != nil {
		panic(err2)
	}
	//var err3 = cmd.Run()
	var err3 = cmd.Start()
	if err3 != nil {
		fmt.Println("cmd.Start() errs", err3)
	}
	io.Copy(os.Stdout, strings.NewReader("aho aho\n"))
	io.Copy(os.Stdout, o1)
	io.Copy(os.Stdout, e2)
	io.Copy(os.Stdout, strings.NewReader("aho aho\n"))
	//os.Stdout.Flush()
	var err4 = cmd.Wait()
	if err4 != nil {
		fmt.Println("cmd.Wait()", err4)
	}
}

// Do exec.Command(), cmd.StdoutPipe(), bufio.NewScanner().
func test_get_lines() {
	fmt.Println("test_get_lines")

	var ch1 = make(chan string)

	var ctx = context.Background()
	var cmd = exec.CommandContext(ctx, "cat", "./LICENSE")
	if cmd == nil {
		panic("cmd=nil")
	}

	var o1, err1 = cmd.StdoutPipe()
	if err1 != nil {
		log.Fatal(err1)
	}
	//var e2, err2 = cmd.StderrPipe()
	//if err2 != nil {
	//log.Fatal(err2)
	//}
	var err3 = cmd.Start()
	if err3 != nil {
		fmt.Println("cmd.Start() errs", err3)
	}

	go func() {
		for {
			var s1, ok1 = <-ch1
			if !ok1 {
				fmt.Println("CLOSED")
				break
			}
			fmt.Println("LINE: ", s1)
		}
	}()

	var sc = bufio.NewScanner(o1)
	for sc.Scan() {
		//var bs = bytes.Clone(sc.Bytes())
		var s2 = sc.Text()
		//fmt.Println("line: ", s2)
		ch1 <- s2
	}
	close(ch1)
}

func test_functions_in_utility_go() {
	fmt.Println("Check sorting strings...")
	var x1 = string_sort([]string{"jkl", "ghi", "def", "abc"})
	fmt.Println("sorted strings=", x1)

	fmt.Println("")
	fmt.Println("Check string-set equal...")
	var s1 = []string{
		"uid", "modification_time", "groups", "enabled", "claim",
	}
	var s2 = string_sort([]string{
		"uid", "claim", "groups", "enabled", "modification_time",
	})
	var eq = string_set_equal(s1, s2)
	fmt.Println("equal=", eq)
}
