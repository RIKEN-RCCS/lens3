/* Test manager.go. */

package lens3

import (
	"context"
	//"encoding/json"
	"fmt"
	//"log"
	"time"
	//"reflect"
	"os"
	"os/exec"
	"os/signal"
	"syscall"
	"testing"
)

func Test_manager(t *testing.T) {
	//test_sigal_handler()
	//start_process_with_timeout()
	collect_process_output()
}

func test_sigal_handler() {
	fmt.Println("Do INT/TERM; Stop by QUIT")

	sig := make(chan bool)
	loop := make(chan error)

	go sig_handler(sig)

	var quit bool
	for {
		go func() {
			time.Sleep(3000 * time.Millisecond)
			loop <- nil
		}()

		select {
		case quit = <-sig:
			fmt.Println("manger quit=", quit)
		case <-loop:
			fmt.Println("manger loop=", quit)
		}
	}
	fmt.Println("manger done")
}

func sig_handler(q chan bool) {
	fmt.Println("sig_handler start")

	c := make(chan os.Signal, 1)
	signal.Notify(c, syscall.SIGINT, syscall.SIGTERM, syscall.SIGHUP)

	//var quit bool
	for signal := range c {
		switch signal {
		case syscall.SIGINT:
			fmt.Println("SIGINT")
			q <- true
		case syscall.SIGTERM:
			fmt.Println("SIGTERM")
			q <- false
		case syscall.SIGHUP:
			fmt.Println("SIGHUP")
			fmt.Println("sig_handler exitting")
			os.Exit(0)
		}
	}
}

func start_process_with_timeout() {
	fmt.Println("start_process_with_timeout")

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

func collect_process_output() {
	fmt.Println("collect_process_output")

	var ctx = context.Background()
	var cmd = exec.CommandContext(ctx, "cat", "manager_test.go")
	var err = cmd.Run()
	if err != nil {
		fmt.Println("cmd.Run() errs")
	}
}
